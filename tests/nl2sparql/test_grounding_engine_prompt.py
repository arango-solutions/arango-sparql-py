"""SC-gate: retrieved grounding entities land in the ENGINE-built prompt.

Mirrors ``test_fewshot_engine_prompt.py``'s SC2 gate for seam 6: the engine's
``_system_prompt`` must compose the "## Known entities" block, and the
standalone ``SparqlAdapter.grammar_prompt_section()`` must stay entity-free
forever (Pitfall 1 — never let grounding leak into the static/cacheable
schema prefix that the Anthropic prompt-cache split treats as the shared
prefix).

Key-free / no-network / no-torch / no-pyoxigraph: the grounding index is
built in-process from a hand-rolled ``GroundedEntity`` list (no instance-
graph fixture needed), and ``_system_prompt`` never fires an LLM completion,
so a bare ``EngineProviderBridge`` around a ``ScriptedLLMClient`` is enough to
satisfy the ``LLMProvider`` protocol without ever calling it.
"""

from __future__ import annotations

from arango_query_core.nl.engine import NLQueryEngine
from arango_query_core.nl.grounding import (
    GroundedEntity,
    GroundedPredicate,
    LabelIndex,
    PredicateIndex,
)

from arango_sparql.nl2sparql.client import ScriptedLLMClient
from arango_sparql.nl2sparql.engine_adapter import EngineProviderBridge, SparqlAdapter
from arango_sparql.nl2sparql.models import LLMResponse
from arango_sparql.translate.resolver import SchemaResolver

ONTOLOGY = """
@prefix : <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Person a owl:Class ; phys:collectionName "Person" .
:name a owl:DatatypeProperty ; rdfs:domain :Person ;
    rdfs:range <http://www.w3.org/2001/XMLSchema#string> .
""".strip()

_SENTINEL_LABEL = "Sentinel Widget XYZ123"


def _build_index() -> LabelIndex:
    return LabelIndex.from_items(
        [GroundedEntity(id="http://ex.org/w1", labels=(_SENTINEL_LABEL,), type="Widget")]
    )


def test_entities_render_in_engine_prompt_not_standalone_builder() -> None:
    index = _build_index()
    adapter = SparqlAdapter(
        resolver=SchemaResolver.from_turtle(ONTOLOGY),
        ontology_ttl=ONTOLOGY,
        grounding_index=index,
    )
    bridge = EngineProviderBridge(ScriptedLLMClient([LLMResponse(content="unused")], latency_ms=0))
    engine = NLQueryEngine(provider=bridge, adapter=adapter, grounding_k=20, max_retries=0)

    # The engine's own render path — no LLM completion is fired by this call.
    system_prompt = engine._system_prompt(f"find the {_SENTINEL_LABEL}", "")

    assert "## Known entities" in system_prompt
    assert _SENTINEL_LABEL in system_prompt

    # Pitfall 1 gate: the standalone PromptBuilder path (grammar_prompt_section)
    # must stay entity-free — grounding never routes through it.
    standalone_prompt = adapter.grammar_prompt_section("")
    assert _SENTINEL_LABEL not in standalone_prompt
    assert "## Known entities" not in standalone_prompt


_SENTINEL_PREDICATE_LABEL = "sentinelPredicateXYZ123"


def _build_predicate_index() -> PredicateIndex:
    return PredicateIndex.from_items(
        [
            GroundedPredicate(
                iri="http://ex.org/sentinelPredicateXYZ123",
                label=_SENTINEL_PREDICATE_LABEL,
                kind="datatype",
                domain="Person",
                range="string",
                shape="literal",
            )
        ]
    )


def test_predicates_render_in_engine_prompt_not_standalone_builder() -> None:
    index = _build_predicate_index()
    adapter = SparqlAdapter(
        resolver=SchemaResolver.from_turtle(ONTOLOGY),
        ontology_ttl=ONTOLOGY,
        predicate_index=index,
    )
    bridge = EngineProviderBridge(ScriptedLLMClient([LLMResponse(content="unused")], latency_ms=0))
    engine = NLQueryEngine(provider=bridge, adapter=adapter, predicate_k=20, max_retries=0)

    # The engine's own render path — no LLM completion is fired by this call.
    system_prompt = engine._system_prompt(f"find the {_SENTINEL_PREDICATE_LABEL}", "")

    assert "## Known schema predicates" in system_prompt
    assert _SENTINEL_PREDICATE_LABEL in system_prompt

    # D-07 cache boundary extended to seam 7: the standalone PromptBuilder
    # path (grammar_prompt_section) must stay predicate-free — the predicate
    # block never routes through it.
    standalone_prompt = adapter.grammar_prompt_section("")
    assert _SENTINEL_PREDICATE_LABEL not in standalone_prompt
    assert "## Known schema predicates" not in standalone_prompt
