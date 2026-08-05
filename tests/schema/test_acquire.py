"""Unit tests for :mod:`arango_sparql.schema.acquire` (PRD §6.3.2).

Covers:

* Strategy dispatch — ``"auto"``, ``"analyzer"``, ``"heuristic"``,
  invalid value.
* Analyzer-installed path: ``AgenticSchemaAnalyzer`` is invoked and
  its output is reshaped into a :class:`MappingBundle`.
* Analyzer-missing path: heuristic fallback runs and attaches the
  ``W_SCHEMA_HEURISTIC_FALLBACK`` warning.
* ``strategy="analyzer"`` with missing extra raises
  :class:`AnalyzerNotInstalledError`.
* ``strategy="heuristic"`` never imports the analyzer (monkeypatch
  guard).
* RPT enrichment merges into the bundle even when the analyzer
  produced it (PRD §6.3.2 step 2).
* Live-DB fingerprint wrappers degrade to ``None`` when the
  analyzer is missing.
* ``include_owl=True`` carries OWL Turtle through to the bundle.
* Acquisition timestamp metadata is populated.

Tests do not touch a live ArangoDB. The ``schema_analyzer`` package
is mocked at the symbol level via ``monkeypatch.setattr`` so the
tests are self-contained and stable regardless of the analyzer
extra's real installation state in the test environment.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import arango_sparql.schema.acquire as acquire_mod
from arango_sparql.schema.acquire import (
    ANALYZER_INSTALL_HINT,
    W_ANALYZER_NOT_INSTALLED,
    W_SCHEMA_HEURISTIC_FALLBACK,
    AnalyzerNotInstalledError,
    Strategy,
    acquire_mapping_bundle,
    analyzer_available,
    db_counts_fingerprint,
    db_shape_fingerprint,
)
from arango_sparql.translate.mapping import MappingBundle

# ---------------------------------------------------------------------------
# Mock database (duck-typed against python-arango's StandardDatabase)
# ---------------------------------------------------------------------------


class _MockAql:
    def __init__(self, samples: dict[str, list[dict[str, Any]]]) -> None:
        self.samples = samples
        self.queries_seen: list[tuple[str, dict[str, Any]]] = []

    def execute(self, query: str, bind_vars: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.queries_seen.append((query, dict(bind_vars or {})))
        if not bind_vars:
            return []
        name = bind_vars.get("@col")
        docs = list(self.samples.get(name, []))
        # RPT type lookup issued by the relationship-synthesis pass:
        # FILTER t[@pred] == @rdftype AND t[@subj] IN @uris RETURN {s, o}
        if "rdftype" in bind_vars:
            pred = bind_vars.get("pred")
            subj = bind_vars.get("subj")
            obj = bind_vars.get("obj")
            rdftype = bind_vars.get("rdftype")
            uris = set(bind_vars.get("uris") or [])
            return [
                {"s": d.get(subj), "o": d.get(obj)}
                for d in docs
                if d.get(pred) == rdftype and d.get(subj) in uris
            ]
        n = int(bind_vars.get("n", 0) or 0)
        return docs[:n]


class MockDb:
    """Minimal ``StandardDatabase`` substitute. Carries a name (used
    by some upstream callers as a cache key) and a collection list
    that ``_list_user_collections`` can iterate over.
    """

    def __init__(
        self,
        collections: list[dict[str, Any]],
        samples: dict[str, list[dict[str, Any]]] | None = None,
        name: str = "test_db",
    ) -> None:
        self._collections = collections
        self.aql = _MockAql(samples or {})
        self.name = name

    def collections(self) -> list[dict[str, Any]]:
        return list(self._collections)


def _doc(name: str) -> dict[str, Any]:
    return {"name": name, "system": False, "type": "document"}


def _edge(name: str) -> dict[str, Any]:
    return {"name": name, "system": False, "type": "edge"}


def _empty_db() -> MockDb:
    """A DB that yields zero user collections — heuristic returns an
    empty bundle. Useful for tests that exercise *acquire* logic
    without caring about the bundle contents.
    """

    return MockDb(collections=[])


def _pg_db() -> MockDb:
    """A two-collection PG DB. Heuristic produces two COLLECTION
    entities with no LPG / RPT signals.
    """

    return MockDb(
        collections=[_doc("Person"), _doc("Company")],
        samples={
            "Person": [{"_key": str(i), "name": f"p{i}", "age": 20 + i} for i in range(5)],
            "Company": [{"_key": str(i), "name": f"c{i}", "founded": 1990 + i} for i in range(5)],
        },
    )


def _rpt_db() -> MockDb:
    """A DB whose ``_triples`` collection looks like the legacy Foxx
    RPT layout. Heuristic alone classifies as RPT; the analyzer
    would not (it doesn't know RPT today).
    """

    triples_docs = [
        {
            "subject_uri": f"ex:s{i}",
            "predicate": f"ex:p{i % 3}",
            "object_uri": f"ex:o{i}",
            "object_value": None,
        }
        for i in range(20)
    ]
    return MockDb(
        collections=[_doc("_triples")],
        samples={"_triples": triples_docs},
    )


_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_EX = "http://example.org/"


def _rpt_typed_db() -> MockDb:
    """An RPT ``_triples`` store carrying ``rdf:type`` rows *and*
    object-property rows, so the relationship-synthesis pass can type
    the endpoints (``Person`` --authored--> ``Doc``).
    """

    def type_row(subject: str, klass: str) -> dict[str, Any]:
        return {
            "subject_uri": _EX + subject,
            "predicate": _RDF_TYPE,
            "object_uri": _EX + klass,
            "object_value": None,
        }

    def obj_row(subject: str, predicate: str, obj: str) -> dict[str, Any]:
        return {
            "subject_uri": _EX + subject,
            "predicate": _EX + predicate,
            "object_uri": _EX + obj,
            "object_value": None,
        }

    triples = [
        type_row("alice", "Person"),
        type_row("bob", "Person"),
        type_row("doc1", "Doc"),
        type_row("doc2", "Doc"),
        obj_row("alice", "authored", "doc1"),
        obj_row("bob", "authored", "doc2"),
    ]
    return MockDb(collections=[_doc("_triples")], samples={"_triples": triples})


# ---------------------------------------------------------------------------
# Analyzer mocking helpers
# ---------------------------------------------------------------------------


def _make_analyzer_mock(
    *,
    conceptual: dict[str, Any] | None = None,
    physical: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[type, Any]:
    """Build an ``AgenticSchemaAnalyzer`` substitute and an
    ``export_mapping`` substitute that produces the analyzer-export
    wire shape (camelCase top-level keys).

    Returned as a (class, callable) pair so each test can monkey-
    patch them independently into ``schema_analyzer``.
    """

    conceptual = conceptual or {
        "entities": [
            {
                "name": "Person",
                "labels": ["Person"],
                "properties": [],
            }
        ],
        "relationships": [],
    }
    physical = physical or {
        "entities": {"Person": {"style": "COLLECTION", "collectionName": "Person"}},
        "relationships": {},
    }
    metadata = metadata or {"source": "schema_analyzer_baseline"}

    class _AnalysisResult:
        def __init__(self) -> None:
            self.conceptual_schema = conceptual
            self.physical_mapping = physical
            # Mirror the v0.6+ pydantic-model surface so
            # _coerce_metadata_to_dict can exercise its `.model_dump`
            # branch for at least one test.
            self.metadata = SimpleNamespace(model_dump=lambda by_alias=False: dict(metadata))

    class FakeAnalyzer:
        # Mirror the real ``AgenticSchemaAnalyzer`` constructor, which the
        # acquire layer now calls with ``llm_provider`` / ``model`` so the
        # analyzer runs its LLM-backed classification (see
        # acquire.py::_resolve_analyzer_provider). Accept and record the
        # kwargs so tests can assert on them if needed.
        def __init__(
            self,
            *,
            llm_provider: str | None = None,
            model: str | None = None,
            **_kwargs: Any,
        ) -> None:
            self.llm_provider = llm_provider
            self.model = model

        def analyze_physical_schema(self, _db: Any, **_kwargs: Any) -> _AnalysisResult:
            # Accept timeout_ms (and any future kwargs) the acquire layer
            # now passes through to the real analyzer.
            return _AnalysisResult()

    def fake_export_mapping(analysis: dict[str, Any], target: str = "cypher") -> dict[str, Any]:
        # Simulate the analyzer's pass-through export — for "cypher"
        # target, the conceptual + physical sub-trees come back
        # unchanged.
        assert target == "cypher", f"acquire layer should request target=cypher, got {target!r}"
        return {
            "conceptualSchema": analysis["conceptualSchema"],
            "physicalMapping": analysis["physicalMapping"],
            "metadata": analysis["metadata"],
        }

    return FakeAnalyzer, fake_export_mapping


def _install_analyzer_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    analyzer_cls: type,
    export_fn: Any,
    owl_fn: Any | None = None,
) -> None:
    """Inject the mock symbols into the real ``schema_analyzer``
    module so the lazy imports inside ``acquire`` resolve to them.
    """

    import schema_analyzer  # imported by acquire on the analyzer path
    import schema_analyzer.owl_export

    monkeypatch.setattr(schema_analyzer, "AgenticSchemaAnalyzer", analyzer_cls)
    monkeypatch.setattr(schema_analyzer, "export_mapping", export_fn)
    if owl_fn is not None:
        monkeypatch.setattr(
            schema_analyzer.owl_export,
            "export_conceptual_model_as_owl_turtle",
            owl_fn,
        )


def _block_schema_analyzer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``import schema_analyzer`` raise ``ImportError`` for the
    duration of one test — simulates an environment where the
    optional extra is not installed.
    """

    # Drop any cached module reference + every submodule so the next
    # import attempt has to resolve from scratch (and will fail
    # because of the meta-path finder we install below).
    for mod_name in list(sys.modules):
        if mod_name == "schema_analyzer" or mod_name.startswith("schema_analyzer."):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    class _BlockSchemaAnalyzer:
        def find_module(self, fullname: str, path: Any = None) -> Any:
            if fullname == "schema_analyzer" or fullname.startswith("schema_analyzer."):
                return self
            return None

        def load_module(self, fullname: str) -> ModuleType:
            raise ImportError(f"schema_analyzer is unavailable in this test (blocked at {fullname!r})")

        # Modern import system — the "find_spec" hook supersedes
        # "find_module"; we implement both for python 3.11.
        def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
            if fullname == "schema_analyzer" or fullname.startswith("schema_analyzer."):
                from importlib.machinery import ModuleSpec

                return ModuleSpec(fullname, self)
            return None

        def create_module(self, spec: Any) -> ModuleType | None:
            raise ImportError(f"schema_analyzer is unavailable in this test (blocked at {spec.name!r})")

        def exec_module(self, module: ModuleType) -> None:
            raise ImportError("schema_analyzer is unavailable in this test")

    finder = _BlockSchemaAnalyzer()
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])


# ---------------------------------------------------------------------------
# Strategy validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "foo", "AUTO", "Heuristic", None])
def test_invalid_strategy_raises_value_error(bad: Any) -> None:
    with pytest.raises(ValueError, match="strategy must be one of"):
        acquire_mapping_bundle(_empty_db(), strategy=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("good", ["auto", "analyzer", "heuristic"])
def test_valid_strategies_are_accepted(good: Strategy, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each documented strategy at least dispatches without raising
    ValueError. We mock the analyzer for "analyzer"/"auto" so the
    test does not depend on a live ArangoDB.
    """

    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_empty_db(), strategy=good)
    assert isinstance(bundle, MappingBundle)


# ---------------------------------------------------------------------------
# Analyzer path
# ---------------------------------------------------------------------------


def test_analyzer_path_produces_bundle_with_analyzer_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer")
    assert bundle.source is not None
    assert bundle.source.kind == "analyzer"
    assert "Person" in (bundle.physical_mapping.get("entities") or {})


def test_analyzer_path_passes_db_to_analyze_physical_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: the analyzer should actually receive the db handle —
    catches a refactor that accidentally drops the argument.
    """

    seen: list[Any] = []

    cls, fn = _make_analyzer_mock()

    class TracingAnalyzer(cls):  # type: ignore[misc, valid-type]
        def analyze_physical_schema(self, db: Any, **kwargs: Any) -> Any:
            seen.append(db)
            return super().analyze_physical_schema(db, **kwargs)

    _install_analyzer_mock(monkeypatch, analyzer_cls=TracingAnalyzer, export_fn=fn)
    db = _empty_db()
    acquire_mapping_bundle(db, strategy="analyzer")
    assert seen == [db]


def test_analyzer_path_with_include_owl_carries_turtle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cls, fn = _make_analyzer_mock()
    owl_value = "@prefix ex: <http://example.org/> .\n"
    _install_analyzer_mock(
        monkeypatch,
        analyzer_cls=cls,
        export_fn=fn,
        owl_fn=lambda _ad: owl_value,
    )
    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer", include_owl=True)
    assert bundle.owl_turtle == owl_value


def test_analyzer_path_with_owl_failure_returns_bundle_without_owl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OWL export is best-effort — failure should not 500 the call."""

    cls, fn = _make_analyzer_mock()

    def boom(_analysis_dict: dict[str, Any]) -> str:
        raise RuntimeError("owl export crashed")

    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn, owl_fn=boom)
    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer", include_owl=True)
    assert bundle.owl_turtle is None


def test_analyzer_path_without_include_owl_does_not_call_owl_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cls, fn = _make_analyzer_mock()
    calls: list[dict[str, Any]] = []

    def tracing_owl(analysis_dict: dict[str, Any]) -> str:
        calls.append(analysis_dict)
        return ""

    _install_analyzer_mock(
        monkeypatch,
        analyzer_cls=cls,
        export_fn=fn,
        owl_fn=tracing_owl,
    )
    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer", include_owl=False)
    assert bundle.owl_turtle is None
    assert calls == []


def test_analyzer_metadata_dict_shape_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older analyzer releases returned ``metadata`` as a plain dict.
    Verify the coercion handles that branch as well as the v0.6+
    pydantic-model branch.
    """

    cls, fn = _make_analyzer_mock(
        metadata={"source": "old-analyzer"},
    )

    class DictMetaAnalyzer(cls):  # type: ignore[misc, valid-type]
        def analyze_physical_schema(self, db: Any, **kwargs: Any) -> Any:
            res = super().analyze_physical_schema(db, **kwargs)
            res.metadata = {"source": "dict-shape"}
            return res

    _install_analyzer_mock(monkeypatch, analyzer_cls=DictMetaAnalyzer, export_fn=fn)
    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer")
    assert bundle.metadata.get("source") == "dict-shape"


def test_analyzer_string_warnings_are_normalized_to_dicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the analyzer can attach a *bare string* advisory
    (e.g. "LLM provider not configured ...") to ``metadata.warnings``.
    The wire contract types every ``warnings`` field as ``list[dict]``,
    so a string entry previously crashed ``SchemaIntrospectResponse``
    validation with an opaque 500. ``acquire_mapping_bundle`` must
    coerce such entries into ``{code, message}`` dicts.
    """

    advisory = "LLM provider not configured; using heuristic baseline inference"
    cls, fn = _make_analyzer_mock(
        metadata={"source": "analyzer", "warnings": [advisory]},
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)

    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer")
    warnings = bundle.metadata.get("warnings") or []
    assert warnings, "expected the analyzer advisory to survive normalization"
    assert all(isinstance(w, dict) for w in warnings), warnings
    assert any(w.get("message") == advisory for w in warnings), warnings


def test_dict_warnings_pass_through_normalization_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A producer that already emits ``{code, message}`` dicts must be
    left untouched — normalization is shape-coercion, not rewriting.
    """

    dict_warning = {"code": "W_SOMETHING", "message": "already structured"}
    cls, fn = _make_analyzer_mock(
        metadata={"source": "analyzer", "warnings": [dict_warning]},
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)

    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer")
    warnings = bundle.metadata.get("warnings") or []
    assert dict_warning in warnings


def test_analyzer_strategy_raises_when_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquire_mod, "analyzer_available", lambda: False)
    with pytest.raises(AnalyzerNotInstalledError) as exc_info:
        acquire_mapping_bundle(_empty_db(), strategy="analyzer")
    assert exc_info.value.install_hint == ANALYZER_INSTALL_HINT
    assert "arangodb-schema-analyzer" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------


def test_auto_strategy_falls_back_to_heuristic_when_analyzer_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquire_mod, "analyzer_available", lambda: False)
    bundle = acquire_mapping_bundle(_pg_db(), strategy="auto")
    assert bundle.source is not None
    assert bundle.source.kind == "heuristic"


def test_auto_fallback_attaches_analyzer_not_installed_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The auto-fallback path attaches ``ANALYZER_NOT_INSTALLED``
    (PRD line 610) carrying the install hint. The bundle's own
    ``W_SCHEMA_HEURISTIC_FALLBACK`` provenance marker is also
    present — both codes coexist on the same bundle.
    """

    monkeypatch.setattr(acquire_mod, "analyzer_available", lambda: False)
    bundle = acquire_mapping_bundle(_pg_db(), strategy="auto")
    warnings = bundle.metadata.get("warnings") or []
    assert any(
        w.get("code") == W_ANALYZER_NOT_INSTALLED and w.get("install_hint") == ANALYZER_INSTALL_HINT
        for w in warnings
    ), f"expected ANALYZER_NOT_INSTALLED warning, got {warnings!r}"
    assert any(w.get("code") == W_SCHEMA_HEURISTIC_FALLBACK for w in warnings), (
        "heuristic provenance marker should still be present"
    )


def test_explicit_heuristic_strategy_omits_install_hint_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator who explicitly opts for heuristic should not see
    the ``ANALYZER_NOT_INSTALLED`` warning — that one is reserved
    for the implicit fallback path. The bundle still carries
    ``W_SCHEMA_HEURISTIC_FALLBACK`` because every heuristic bundle
    advertises its provenance.
    """

    monkeypatch.setattr(acquire_mod, "analyzer_available", lambda: True)
    bundle = acquire_mapping_bundle(_pg_db(), strategy="heuristic")
    warnings = bundle.metadata.get("warnings") or []
    assert not any(w.get("code") == W_ANALYZER_NOT_INSTALLED for w in warnings)
    assert any(w.get("code") == W_SCHEMA_HEURISTIC_FALLBACK for w in warnings)


def test_heuristic_strategy_never_calls_analyzer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with the analyzer installed, ``strategy="heuristic"``
    must not import or call it — verified via a sentinel that
    raises if the analyzer code path is reached.
    """

    def boom(*_: Any, **__: Any) -> Any:
        raise AssertionError("analyzer should not have been touched in heuristic mode")

    import schema_analyzer

    monkeypatch.setattr(schema_analyzer, "AgenticSchemaAnalyzer", boom)
    monkeypatch.setattr(schema_analyzer, "export_mapping", boom)
    bundle = acquire_mapping_bundle(_pg_db(), strategy="heuristic")
    assert isinstance(bundle, MappingBundle)


# ---------------------------------------------------------------------------
# RPT enrichment (PRD §6.3.2 step 2)
# ---------------------------------------------------------------------------


def test_rpt_enrichment_adds_rpt_entry_to_analyzer_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The analyzer alone classifies ``_triples`` as a regular doc
    collection. The RPT enrichment pass must override that with a
    style="RPT" entry so the SPARQL→AQL planner takes the right
    branch.
    """

    # Analyzer mock claims `_triples` is a normal COLLECTION.
    cls, fn = _make_analyzer_mock(
        conceptual={"entities": [], "relationships": []},
        physical={
            "entities": {
                "_triples": {
                    "style": "COLLECTION",
                    "collectionName": "_triples",
                }
            },
            "relationships": {},
        },
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_rpt_db(), strategy="analyzer")
    entities = bundle.physical_mapping.get("entities") or {}
    assert "_triples" in entities
    rpt_entry = entities["_triples"]
    assert rpt_entry["style"] == "RPT"
    assert rpt_entry["triplesCollection"] == "_triples"
    assert rpt_entry["subjectColumn"] == "subject_uri"
    assert rpt_entry["predicateColumn"] == "predicate"
    assert rpt_entry["objectUriColumn"] == "object_uri"
    assert rpt_entry["objectValueColumn"] == "object_value"
    assert "rptCoverage" in rpt_entry


def test_rpt_enrichment_tags_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_rpt_db(), strategy="analyzer")
    detected = bundle.metadata.get("detectedPatterns") or []
    assert "rpt" in detected
    enrichment = bundle.metadata.get("enrichmentApplied") or []
    assert any(
        e.get("kind") == "rpt_overlay" and "_triples" in (e.get("collections") or []) for e in enrichment
    )


def test_rpt_enrichment_synthesizes_typed_object_property_relationships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The enrichment pass connects an RPT object property to its
    typed endpoints — the cross-collection inference the analyzer's
    PG/LPG classification and the bare RPT entity overlay both miss.
    """

    # Analyzer declares no relationships; enrichment must supply them.
    cls, fn = _make_analyzer_mock(
        conceptual={"entities": [], "relationships": []},
        physical={"entities": {}, "relationships": {}},
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_rpt_typed_db(), strategy="analyzer")

    relationships = bundle.physical_mapping.get("relationships") or {}
    assert "authored" in relationships
    authored = relationships["authored"]
    assert authored["style"] == "RPT_EDGE"
    assert authored["fromEntity"] == "Person"
    assert authored["toEntity"] == "Doc"
    assert authored["triplesCollection"] == "_triples"

    # The synthesized relationship names are recorded for observability.
    enrichment = bundle.metadata.get("enrichmentApplied") or []
    assert any("authored" in (e.get("relationships") or []) for e in enrichment)


def test_rpt_enrichment_does_not_clobber_existing_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If an upstream producer already declared a relationship of the
    same name, synthesis must not overwrite it (additive ``setdefault``
    contract).
    """

    sentinel = {"style": "RPT_EDGE", "fromEntity": "Curated", "toEntity": "Curated"}
    cls, fn = _make_analyzer_mock(
        conceptual={"entities": [], "relationships": []},
        physical={"entities": {}, "relationships": {"authored": sentinel}},
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_rpt_typed_db(), strategy="analyzer")
    relationships = bundle.physical_mapping.get("relationships") or {}
    assert relationships["authored"] == sentinel


def test_rpt_enrichment_skipped_when_no_rpt_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pure-PG DB should pass through with no RPT-related metadata
    keys — verifies the enrichment pass is additive (not always-on).
    """

    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_pg_db(), strategy="analyzer")
    detected = bundle.metadata.get("detectedPatterns") or []
    assert "rpt" not in detected
    assert "enrichmentApplied" not in bundle.metadata


# ---------------------------------------------------------------------------
# Edge-endpoint enrichment (producer-agnostic)
# ---------------------------------------------------------------------------


def _pg_edge_db() -> MockDb:
    """PG DB with a ``Person`` collection and a dedicated ``knows`` edge
    whose ``_from`` / ``_to`` both land in ``Person``.
    """

    persons = [{"_key": str(i), "name": f"p{i}"} for i in range(5)]
    knows = [{"_from": f"Person/{i}", "_to": f"Person/{i + 1}"} for i in range(4)]
    return MockDb(
        collections=[_doc("Person"), _edge("knows")],
        samples={"Person": persons, "knows": knows},
    )


def test_edge_endpoint_enrichment_fills_any_on_analyzer_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The analyzer leaves the edge relationship's endpoints ``"Any"``;
    the always-on enrichment resolves them from ``_from`` / ``_to``.
    """

    cls, fn = _make_analyzer_mock(
        conceptual={"entities": [], "relationships": []},
        physical={
            "entities": {"Person": {"style": "COLLECTION", "collectionName": "Person"}},
            "relationships": {
                "knows": {
                    "style": "DEDICATED_COLLECTION",
                    "edgeCollectionName": "knows",
                    "fromEntity": "Any",
                    "toEntity": "Any",
                }
            },
        },
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_pg_edge_db(), strategy="analyzer")

    knows = (bundle.physical_mapping.get("relationships") or {})["knows"]
    assert knows["fromEntity"] == "Person"
    assert knows["toEntity"] == "Person"
    enrichment = bundle.metadata.get("enrichmentApplied") or []
    assert any(
        e.get("kind") == "edge_endpoint_inference" and "knows" in (e.get("relationships") or [])
        for e in enrichment
    )


def test_edge_endpoint_enrichment_never_overwrites_pinned_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``fromEntity`` the producer already pinned is preserved; only
    the still-``"Any"`` side is filled.
    """

    cls, fn = _make_analyzer_mock(
        conceptual={"entities": [], "relationships": []},
        physical={
            "entities": {"Person": {"style": "COLLECTION", "collectionName": "Person"}},
            "relationships": {
                "knows": {
                    "style": "DEDICATED_COLLECTION",
                    "edgeCollectionName": "knows",
                    "fromEntity": "Curated",
                    "toEntity": "Any",
                }
            },
        },
    )
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_pg_edge_db(), strategy="analyzer")

    knows = (bundle.physical_mapping.get("relationships") or {})["knows"]
    assert knows["fromEntity"] == "Curated"
    assert knows["toEntity"] == "Person"


def test_edge_endpoint_enrichment_noop_when_no_relationships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pure-PG DB with no edge relationships gets no endpoint-inference
    metadata — the pass is a no-op when there's nothing to fill.
    """

    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    bundle = acquire_mapping_bundle(_pg_db(), strategy="analyzer")
    enrichment = bundle.metadata.get("enrichmentApplied") or []
    assert not any(e.get("kind") == "edge_endpoint_inference" for e in enrichment)


def test_rpt_enrichment_is_safe_when_detect_throws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing RPT pass must not propagate — the bundle is
    returned untouched. Confirms the defensive try/except contract.
    """

    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    monkeypatch.setattr(
        acquire_mod,
        "detect_rpt_pattern",
        lambda _db, **_kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    bundle = acquire_mapping_bundle(_pg_db(), strategy="analyzer")
    assert isinstance(bundle, MappingBundle)
    # The analyzer-supplied entity is preserved; no RPT keys appear.
    entities = bundle.physical_mapping.get("entities") or {}
    assert any(spec.get("style") == "COLLECTION" for spec in entities.values())


# ---------------------------------------------------------------------------
# Acquisition timestamp
# ---------------------------------------------------------------------------


def test_acquisition_timestamp_is_stamped_on_analyzer_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    when = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    bundle = acquire_mapping_bundle(_empty_db(), strategy="analyzer", now=when)
    assert bundle.metadata.get("acquisitionTimestamp") == when.isoformat()


def test_force_refresh_flag_is_a_no_op_at_acquire_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``force_refresh`` is documented as an accept-and-ignore flag
    here (cache is the layer that consumes it). The bundle should
    be identical with or without the flag.
    """

    cls, fn = _make_analyzer_mock()
    _install_analyzer_mock(monkeypatch, analyzer_cls=cls, export_fn=fn)
    when = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    a = acquire_mapping_bundle(_empty_db(), strategy="analyzer", force_refresh=False, now=when)
    b = acquire_mapping_bundle(_empty_db(), strategy="analyzer", force_refresh=True, now=when)
    assert a.metadata.get("acquisitionTimestamp") == b.metadata.get("acquisitionTimestamp")


# ---------------------------------------------------------------------------
# analyzer_available() probe
# ---------------------------------------------------------------------------


def test_analyzer_available_true_when_extra_installed() -> None:
    """In our test venv the analyzer extra is installed, so the
    probe should return True. If a CI env removes the extra, this
    test will need to be skipped via a marker.
    """

    assert analyzer_available() is True


def test_analyzer_available_false_when_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_schema_analyzer(monkeypatch)
    assert analyzer_available() is False


# ---------------------------------------------------------------------------
# Live-DB fingerprint wrappers
# ---------------------------------------------------------------------------


def test_db_shape_fingerprint_returns_value_when_analyzer_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import schema_analyzer

    monkeypatch.setattr(
        schema_analyzer,
        "fingerprint_physical_shape",
        lambda _db, exclude_collections=None: "shape-fp-12345",
    )
    assert db_shape_fingerprint(_empty_db()) == "shape-fp-12345"


def test_db_counts_fingerprint_returns_value_when_analyzer_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import schema_analyzer

    monkeypatch.setattr(
        schema_analyzer,
        "fingerprint_physical_counts",
        lambda _db, exclude_collections=None: "counts-fp-67890",
    )
    assert db_counts_fingerprint(_empty_db()) == "counts-fp-67890"


def test_db_shape_fingerprint_returns_none_when_analyzer_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_schema_analyzer(monkeypatch)
    assert db_shape_fingerprint(_empty_db()) is None


def test_db_counts_fingerprint_returns_none_when_analyzer_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_schema_analyzer(monkeypatch)
    assert db_counts_fingerprint(_empty_db()) is None


def test_db_shape_fingerprint_excludes_l2_cache_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache-self-loop guard: the shape fingerprint must exclude the
    L2 cache collection so writing the cache row does not
    invalidate the fingerprint that just landed in it.
    """

    import schema_analyzer

    seen: dict[str, Any] = {}

    def fake_shape(_db: Any, exclude_collections: set[str] | None = None) -> str:
        seen["exclude"] = exclude_collections
        return "ok"

    monkeypatch.setattr(schema_analyzer, "fingerprint_physical_shape", fake_shape)
    db_shape_fingerprint(_empty_db())
    assert seen["exclude"] == {"arango_sparql_schema_cache"}


def test_db_counts_fingerprint_handles_old_analyzer_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older analyzer releases (< 0.5) did not accept the
    ``exclude_collections`` kwarg. The wrapper should fall back to
    calling without the kwarg rather than failing outright.
    """

    import schema_analyzer

    def old_signature(_db: Any) -> str:
        return "compat-fp"

    monkeypatch.setattr(schema_analyzer, "fingerprint_physical_counts", old_signature)
    assert db_counts_fingerprint(_empty_db()) == "compat-fp"


def test_db_shape_fingerprint_returns_none_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: unexpected exceptions from the analyzer should
    degrade to None rather than propagating into the cache layer.
    """

    import schema_analyzer

    def explode(_db: Any, exclude_collections: set[str] | None = None) -> str:
        raise RuntimeError("analyzer disk full")

    monkeypatch.setattr(schema_analyzer, "fingerprint_physical_shape", explode)
    assert db_shape_fingerprint(_empty_db()) is None


# ---------------------------------------------------------------------------
# AnalyzerNotInstalledError carries hint
# ---------------------------------------------------------------------------


def test_analyzer_not_installed_error_default_install_hint() -> None:
    err = AnalyzerNotInstalledError()
    assert err.install_hint == ANALYZER_INSTALL_HINT
    assert "arangodb-schema-analyzer" in str(err)


def test_analyzer_not_installed_error_custom_install_hint() -> None:
    custom = "uv add 'arangodb-schema-analyzer[full]'"
    err = AnalyzerNotInstalledError(install_hint=custom)
    assert err.install_hint == custom
    assert custom in str(err)
