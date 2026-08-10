"""Unit tests for the shared-engine adapter seams.

Covers the two pieces the Wave 3 pipeline re-point injects into
:class:`arango_query_core.nl.engine.NLQueryEngine`:

* :class:`EngineProviderBridge` — LLMClient → LLMProvider adaptation plus
  per-call :class:`LLMCallRecord` audit accounting (success + transport
  failure).
* :class:`SparqlAdapter` — the five ``QueryLanguageAdapter`` seams, proven to
  (a) satisfy the protocol, (b) validate against the INJECTED resolver (the
  resolver-parity invariant that closes the mapping-JSON blocker), and
  (c) reproduce ``baseline.json`` verdicts exactly when driven by the engine.

No network: everything runs through :class:`ScriptedLLMClient`.
"""

from __future__ import annotations

import json

import pytest
import yaml
from arango_query_core.nl import FewShotIndex
from arango_query_core.nl.engine import NLQueryEngine
from arango_query_core.nl.grounding import GroundedEntity, LabelIndex
from arango_query_core.nl.providers import LLMProvider
from arango_query_core.nl.seams import QueryLanguageAdapter

from arango_sparql.api import translate
from arango_sparql.nl2sparql import engine_adapter
from arango_sparql.nl2sparql.client import ScriptedLLMClient
from arango_sparql.nl2sparql.cost import estimate_llm_cost_usd
from arango_sparql.nl2sparql.engine_adapter import EngineProviderBridge, SparqlAdapter
from arango_sparql.nl2sparql.models import LLMResponse
from arango_sparql.nl2sparql.pipeline import NlPipeline
from arango_sparql.translate.resolver import SchemaResolver
from tests.nl2sparql.eval.runner import EVAL_DIR, _canonical

ONTOLOGY = """
@prefix : <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Person a owl:Class ; phys:collectionName "Person" .
:name a owl:DatatypeProperty ; rdfs:domain :Person ;
    rdfs:range <http://www.w3.org/2001/XMLSchema#string> .
""".strip()

# A mapping-shaped ontology: the physical collection name differs from the
# class local name, so AQL over a *populated* resolver mentions "PhysWidgets"
# while an empty-graph resolver falls back to the local name "Widget".
MAPPING_ONTOLOGY = """
@prefix : <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .

:Widget a owl:Class ; phys:collectionName "PhysWidgets" .
""".strip()

WIDGET_QUERY = "PREFIX : <http://ex.org/>\nSELECT ?s WHERE { ?s a :Widget }"
GOOD_QUERY = "PREFIX : <http://ex.org/>\nSELECT ?s WHERE { ?s a :Person }"
BAD_QUERY = "SELECT WHERE { broken"
UNSUPPORTED_QUERY = (
    "PREFIX : <http://ex.org/>\nSELECT ?s WHERE { SERVICE <http://other.example/sparql> { ?s a :Person } }"
)


def _wrap(sparql: str) -> str:
    return f"```sparql\n{sparql.strip()}\n```"


def _resp(content: str, *, prompt: int = 100, completion: int = 50) -> LLMResponse:
    return LLMResponse(
        content=content,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


# ---------------------------------------------------------------------------
# EngineProviderBridge
# ---------------------------------------------------------------------------


class TestEngineProviderBridge:
    def test_bridge_satisfies_llmprovider_protocol(self) -> None:
        bridge = EngineProviderBridge(ScriptedLLMClient([_resp(_wrap(GOOD_QUERY))], latency_ms=0))
        assert isinstance(bridge, LLMProvider)

    def test_bridge_records_one_record_per_call(self) -> None:
        client = ScriptedLLMClient(
            [_resp("hi", prompt=100, completion=50)],
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=0,
        )
        bridge = EngineProviderBridge(client)
        content, usage = bridge.generate("sys", "user")

        assert content == "hi"
        assert len(bridge.records) == 1
        record = bridge.records[0]
        assert record.provider == "openai"
        assert record.model == "gpt-4o-mini"
        assert record.prompt_tokens == 100
        assert record.completion_tokens == 50
        assert record.error is None

    def test_bridge_forwards_message_shape_and_usage_keys(self) -> None:
        client = ScriptedLLMClient([_resp("hi")], latency_ms=0)
        bridge = EngineProviderBridge(client)
        _, usage = bridge.generate("SYSTEM", "USER")

        # The wrapped client saw exactly [system, user] in order.
        assert client.calls == [
            [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "USER"}]
        ]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"):
            assert key in usage
            assert isinstance(usage[key], int)

    def test_bridge_cost_matches_estimator(self) -> None:
        client = ScriptedLLMClient(
            [_resp("hi", prompt=1000, completion=500)],
            provider="openai",
            model="gpt-4o",
            latency_ms=0,
        )
        bridge = EngineProviderBridge(client)
        bridge.generate("sys", "user")

        expected = estimate_llm_cost_usd("openai", "gpt-4o", 1000, 500)
        assert bridge.records[0].cost_usd == expected
        assert bridge.records[0].cost_usd == pytest.approx(0.0075, abs=1e-6)

    def test_bridge_transport_failure_records_and_reraises(self) -> None:
        client = ScriptedLLMClient([RuntimeError("boom")], latency_ms=0)
        bridge = EngineProviderBridge(client)

        with pytest.raises(RuntimeError, match="boom"):
            bridge.generate("sys", "user")

        assert len(bridge.records) == 1
        record = bridge.records[0]
        assert record.error is not None
        assert "boom" in record.error
        assert record.cost_usd == 0.0


# ---------------------------------------------------------------------------
# SparqlAdapter — protocol + seam behavior
# ---------------------------------------------------------------------------


class TestSparqlAdapterSeams:
    def test_adapter_satisfies_protocol(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        assert isinstance(adapter, QueryLanguageAdapter)
        assert adapter.language == "sparql"

    def test_validate_good_query_is_ok(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        result = adapter.validate(GOOD_QUERY)
        assert result.ok is True

    def test_validate_parse_error_carries_code(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        result = adapter.validate(BAD_QUERY)
        assert result.ok is False
        assert result.code == "E_SPARQL_PARSE"

    def test_repair_hint_parse_case_contains_code(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        failure = adapter.validate(BAD_QUERY)
        hint = adapter.repair_hint(BAD_QUERY, failure)
        assert "[E_SPARQL_PARSE]" in hint

    def test_repair_hint_unsupported_case_contains_code_and_sparql11(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        failure = adapter.validate(UNSUPPORTED_QUERY)
        assert failure.code == "E_SPARQL_UNSUPPORTED"
        hint = adapter.repair_hint(UNSUPPORTED_QUERY, failure)
        assert "[E_SPARQL_UNSUPPORTED]" in hint
        assert "SPARQL 1.1" in hint

    def test_guardrails_allow_all(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        verdict = adapter.guardrails(GOOD_QUERY, {})
        assert verdict.allowed is True

    def test_few_shot_index_returns_populated_index(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        index = adapter.few_shot_index()
        assert index is not None
        assert isinstance(index, FewShotIndex)

    def test_grounding_index_returns_injected_index(self) -> None:
        grounding_index = LabelIndex.from_items(
            [GroundedEntity(id="http://ex.org/p1", labels=("Alice",), type="Person")]
        )
        adapter = SparqlAdapter(
            resolver=SchemaResolver.from_turtle(ONTOLOGY),
            ontology_ttl=ONTOLOGY,
            grounding_index=grounding_index,
        )
        assert adapter.grounding_index() is grounding_index

    def test_grounding_index_defaults_to_none(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        assert adapter.grounding_index() is None

    def test_path_index_returns_injected_index(self) -> None:
        from arango_query_core.nl.pathindex import ClassPathIndex

        path_index = ClassPathIndex(edges=[], subclass_of=[])
        adapter = SparqlAdapter(
            resolver=SchemaResolver.from_turtle(ONTOLOGY),
            ontology_ttl=ONTOLOGY,
            path_index=path_index,
        )
        assert adapter.path_index() is path_index

    def test_path_index_defaults_to_none(self) -> None:
        adapter = SparqlAdapter(resolver=SchemaResolver.from_turtle(ONTOLOGY), ontology_ttl=ONTOLOGY)
        assert adapter.path_index() is None

    def test_path_prompt_section_empty_when_anchor_unresolved(self) -> None:
        """No grounding_index injected -> no anchor classes -> '' (D-02 honest no-op)."""
        from arango_query_core.nl.grounding import GroundedPredicate, PredicateIndex
        from arango_query_core.nl.pathindex import ClassPathIndex

        predicates = PredicateIndex.from_items(
            [
                GroundedPredicate(
                    iri="http://ex.org/hasWidgetTarget",
                    label="hasWidgetTarget",
                    kind="object",
                    domain="Widget",
                    range="Gadget",
                    shape="linked_entity",
                )
            ]
        )
        path_index = ClassPathIndex(edges=[("hasWidgetTarget", "Widget", "Gadget")], subclass_of=[])
        adapter = SparqlAdapter(
            resolver=SchemaResolver.from_turtle(ONTOLOGY),
            ontology_ttl=ONTOLOGY,
            predicate_index=predicates,
        )
        assert adapter.path_prompt_section("find hasWidgetTarget", path_index, k=5) == ""

    def test_path_prompt_section_empty_when_target_unresolved(self) -> None:
        """No predicate_index injected -> no targets -> '' (D-02 honest no-op)."""
        from arango_query_core.nl.grounding import GroundedEntity, LabelIndex
        from arango_query_core.nl.pathindex import ClassPathIndex

        grounding = LabelIndex.from_items(
            [GroundedEntity(id="http://ex.org/w1", labels=("Alice",), type="Widget")]
        )
        path_index = ClassPathIndex(edges=[("hasWidgetTarget", "Widget", "Gadget")], subclass_of=[])
        adapter = SparqlAdapter(
            resolver=SchemaResolver.from_turtle(ONTOLOGY),
            ontology_ttl=ONTOLOGY,
            grounding_index=grounding,
        )
        assert adapter.path_prompt_section("find Alice", path_index, k=5) == ""


# ---------------------------------------------------------------------------
# Pipeline threading (Pitfall 5) — path_k/path_index reach the engine
# ---------------------------------------------------------------------------


class TestPipelinePathThreading:
    def test_pipeline_threads_path_index_without_typeerror(self) -> None:
        """Constructing NlPipeline with path_index= and calling .run() must
        not raise TypeError -- the offline structural proof that Plan 03's
        --dry-run will exercise (Pitfall 5)."""
        from arango_query_core.nl.pathindex import ClassPathIndex

        path_index = ClassPathIndex(edges=[], subclass_of=[])
        client = ScriptedLLMClient([_resp(_wrap(GOOD_QUERY))], latency_ms=0)
        pipeline = NlPipeline(
            client=client,
            resolver=SchemaResolver.from_turtle(ONTOLOGY),
            ontology_ttl=ONTOLOGY,
            path_k=5,
            path_index=path_index,
        )
        outcome = pipeline.run("find Person")
        assert outcome.aql


# ---------------------------------------------------------------------------
# Resolver parity — the mapping-JSON blocker
# ---------------------------------------------------------------------------


class TestResolverParity:
    def test_validate_uses_injected_resolver_not_ontology_ttl(self, monkeypatch) -> None:
        """A mapping-only shape (populated resolver, blank ontology_ttl) must
        validate against the INJECTED resolver — proven by (1) an identity spy
        on the translate() call and (2) parity with a direct translate()."""
        populated = SchemaResolver.from_turtle(MAPPING_ONTOLOGY)
        adapter = SparqlAdapter(resolver=populated, ontology_ttl="")

        captured: dict[str, object] = {}
        real_translate = engine_adapter._api_translate

        def _spy(query, *, resolver, **kwargs):
            captured["resolver"] = resolver
            return real_translate(query, resolver=resolver, **kwargs)

        monkeypatch.setattr(engine_adapter, "_api_translate", _spy)

        result = adapter.validate(WIDGET_QUERY)

        # validate() forwarded the exact injected resolver object.
        assert captured["resolver"] is populated
        # And its verdict matches translating directly with that resolver.
        direct = real_translate(WIDGET_QUERY, resolver=populated)
        assert result.ok is True
        assert bool(direct.aql) is True

    def test_populated_and_empty_resolvers_differ(self) -> None:
        """Sanity / negative control: the populated resolver maps :Widget to
        the physical collection, while an empty-graph resolver rejects the
        undeclared class outright. So an adapter that rebuilt its resolver from
        a blank ontology_ttl WOULD diverge — validate() would return ok=False
        instead of ok=True."""
        from arango_sparql.errors import SchemaResolutionError

        populated = SchemaResolver.from_turtle(MAPPING_ONTOLOGY)
        empty = SchemaResolver.from_turtle("")

        mapped_aql = translate(WIDGET_QUERY, resolver=populated).aql
        assert "PhysWidgets" in mapped_aql

        # The empty resolver (what a blank ontology_ttl would rebuild) rejects
        # the query — proving the injected resolver is what makes validate() ok.
        with pytest.raises(SchemaResolutionError):
            translate(WIDGET_QUERY, resolver=empty)


# ---------------------------------------------------------------------------
# Verdict reproduction — engine + bridge + adapter == baseline.json
# ---------------------------------------------------------------------------


class TestVerdictReproduction:
    def test_engine_reproduces_baseline_verdicts(self) -> None:
        corpus = yaml.safe_load((EVAL_DIR / "corpus.yml").read_text())
        baseline = json.loads((EVAL_DIR / "baseline.json").read_text())["configs"]["scripted"]["cases"]
        default_ontology = corpus.get("ontology", "")

        passed = 0
        for case in corpus["cases"]:
            name = case["name"]
            scripted = case.get("scripted", case["expected"])
            ontology = case.get("ontology", default_ontology)
            resolver = SchemaResolver.from_turtle(ontology)
            adapter = SparqlAdapter(resolver=resolver, ontology_ttl=ontology)
            bridge = EngineProviderBridge(ScriptedLLMClient([_resp(_wrap(scripted))], latency_ms=0))
            engine = NLQueryEngine(provider=bridge, adapter=adapter, few_shot_k=0, max_retries=2)

            res = engine.generate(case["nl"], schema_context="")
            if case.get("expect_refusal"):
                # Mirrors tests/nl2sparql/eval/runner.py::_judge's inverted
                # refusal branch (added in 06.2, after this test was first
                # written): a negative case PASSES iff the engine produced NO
                # validated/transpilable query — never compare against the
                # human-rationale ``expected`` prose as if it were SPARQL.
                engine_pass = not res.ok
            else:
                expected_canonical = _canonical(case["expected"])
                actual_canonical = _canonical(res.query) if res.query else None
                engine_pass = bool(
                    res.ok and expected_canonical is not None and expected_canonical == actual_canonical
                )
            passed += int(engine_pass)

            assert engine_pass == bool(baseline[name]), (
                f"case {name!r}: engine verdict {engine_pass} != baseline {baseline[name]}"
            )

        pass_rate = passed / len(corpus["cases"])
        # Compare against the CURRENT scripted baseline's own pass-rate (derived
        # from ``baseline.json``, not a hardcoded number) so this assertion never
        # goes stale again as the corpus grows — the per-case loop above is the
        # real regression gate; this is just the aggregate sanity check.
        expected_pass_rate = sum(1 for v in baseline.values() if v) / len(baseline)
        assert pass_rate == pytest.approx(expected_pass_rate, abs=1e-9)
