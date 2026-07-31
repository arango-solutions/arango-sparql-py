"""Phase 07.5 Plan 02 Task 1 -- unit coverage for ``bank_generator.py``'s 9
real ``ShapeTemplate`` closures (``applies``/``build_sparql``).

Hand-crafted ``binding`` dicts (never going through a data-binding
pipeline -- that lands in Task 2) exercise every shape's ``build_sparql``
in isolation, proving each closure:

- parses (``_canonical`` is not ``None``);
- never emits an instance-namespace IRI (``prodi:``-style);
- name-anchors via ``rdfs:label`` wherever a label filler is used;
- carries NO hardcoded CK25 vocabulary term -- re-run against a second,
  completely synthetic (non-CK25) ontology's own IRIs, every closure
  still parses cleanly and references only that ontology's own
  namespace + the well-known ``rdfs:label``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pyoxigraph", reason="[dev] extra required for the eval-only oxi helpers")

from tests.nl2sparql.eval.bank_generator import RDFS_LABEL_IRI, SHAPE_CATALOG
from tests.nl2sparql.eval.runner import _canonical

_PV = "http://ld.company.org/prod-vocab/"
_PRODI = "http://ld.company.org/prod-instances/"

_SHAPE_NAMES = [t.name for t in SHAPE_CATALOG]


def _shape(name: str):
    return next(t for t in SHAPE_CATALOG if t.name == name)


# --------------------------------------------------------------------------
# Direct build_sparql closure tests (hand-crafted bindings) -- every
# closure must parse and be instance-IRI-free for REAL CK25 IRIs.
# --------------------------------------------------------------------------

_CK25_BINDINGS: dict[str, dict] = {
    "lookup": {"predicate_iri": f"{_PV}addressCountry", "filler_label": "Acme Corp"},
    "value_object": {
        "predicate_iri": f"{_PV}price",
        "hop_predicate_iri": f"{_PV}amount",
        "filler_label": "Widget-1",
    },
    "category_filter": {
        "range_iri": f"{_PV}ProductCategory",
        "predicate_iri": f"{_PV}hasCategory",
        "filler_label": "Crystal",
    },
    "scalar_count": {
        "range_iri": f"{_PV}ProductCategory",
        "predicate_iri": f"{_PV}hasCategory",
        "filler_label": "Crystal",
    },
    "grouped_aggregation": {"predicate_iri": f"{_PV}hasCategory", "threshold": 5},
    "top_n": {"domain_iri": f"{_PV}Hardware", "predicate_iri": f"{_PV}amount"},
    "offset": {"domain_iri": f"{_PV}Hardware", "predicate_iri": f"{_PV}amount"},
    "negation": {"domain_iri": f"{_PV}Supplier", "predicate_iri": f"{_PV}country"},
    "two_hop": {
        "range_iri": f"{_PV}Department",
        "predicate_iri": f"{_PV}memberOf",
        "hop_predicate_iri": f"{_PV}hasManager",
        "filler_label": "Engineering",
    },
}


def test_shape_catalog_has_nine_real_closures() -> None:
    assert len(SHAPE_CATALOG) == 9
    assert len(set(_SHAPE_NAMES)) == 9
    for shape in SHAPE_CATALOG:
        assert shape.applies.__name__ != "_unimplemented_applies"
        assert shape.build_sparql.__name__ != "_unimplemented_build_sparql"


@pytest.mark.parametrize("shape_name", _SHAPE_NAMES)
def test_build_sparql_parses_for_every_shape(shape_name: str) -> None:
    shape = _shape(shape_name)
    query = shape.build_sparql(_CK25_BINDINGS[shape_name])
    assert _canonical(query) is not None, f"{shape_name}: build_sparql output failed to parse:\n{query}"


@pytest.mark.parametrize("shape_name", _SHAPE_NAMES)
def test_build_sparql_never_emits_instance_namespace_iri(shape_name: str) -> None:
    shape = _shape(shape_name)
    query = shape.build_sparql(_CK25_BINDINGS[shape_name])
    assert _PRODI not in query, f"{shape_name}: build_sparql leaked an instance-namespace IRI:\n{query}"
    # Name-anchoring: every shape needing a label filler must reference
    # rdfs:label (never a hardcoded per-schema label predicate).
    if "filler_label" in _CK25_BINDINGS[shape_name]:
        assert RDFS_LABEL_IRI in query, f"{shape_name}: expected rdfs:label name-anchor, got:\n{query}"


def test_grouped_aggregation_distinct_from_scalar_count() -> None:
    """Spike carry-forward #2: grouped_aggregation MUST be a distinct
    shape (GROUP BY + HAVING) from scalar_count (a plain COUNT), never
    collapsed into one -- the ck25-30 regression proved scalar-COUNT
    coverage does not cover HAVING and can distract it."""
    grouped_query = _shape("grouped_aggregation").build_sparql(_CK25_BINDINGS["grouped_aggregation"])
    count_query = _shape("scalar_count").build_sparql(_CK25_BINDINGS["scalar_count"])

    assert "GROUP BY" in grouped_query and "HAVING" in grouped_query
    assert "GROUP BY" not in count_query and "HAVING" not in count_query
    assert "COUNT" in count_query
    assert _canonical(grouped_query) != _canonical(count_query)


# --------------------------------------------------------------------------
# Schema-agnostic proof -- every closure re-run against a SECOND,
# synthetic (non-CK25) ontology must produce valid, IRI-consistent SPARQL
# with NO leaked CK25 vocabulary term baked into the closure itself.
# --------------------------------------------------------------------------

_EX = "http://ex.org/"

_SYNTHETIC_BINDINGS: dict[str, dict] = {
    "lookup": {"predicate_iri": f"{_EX}weight", "filler_label": "Gizmo"},
    "value_object": {
        "predicate_iri": f"{_EX}cost",
        "hop_predicate_iri": f"{_EX}amount",
        "filler_label": "Gizmo",
    },
    "category_filter": {
        "range_iri": f"{_EX}Category",
        "predicate_iri": f"{_EX}hasCategory",
        "filler_label": "Electronics",
    },
    "scalar_count": {
        "range_iri": f"{_EX}Category",
        "predicate_iri": f"{_EX}hasCategory",
        "filler_label": "Electronics",
    },
    "grouped_aggregation": {"predicate_iri": f"{_EX}hasCategory", "threshold": 3},
    "top_n": {"domain_iri": f"{_EX}Widget", "predicate_iri": f"{_EX}weight"},
    "offset": {"domain_iri": f"{_EX}Widget", "predicate_iri": f"{_EX}weight"},
    "negation": {"domain_iri": f"{_EX}Widget", "predicate_iri": f"{_EX}owner"},
    "two_hop": {
        "range_iri": f"{_EX}Department",
        "predicate_iri": f"{_EX}memberOf",
        "hop_predicate_iri": f"{_EX}manages",
        "filler_label": "Sales",
    },
}

_CK25_VOCAB_MARKERS = ("prod-vocab", "prod-instances", "pv:", "Engineering", "Resistor", "Crystal")


@pytest.mark.parametrize("shape_name", _SHAPE_NAMES)
def test_build_sparql_is_schema_agnostic_on_synthetic_ontology(shape_name: str) -> None:
    """No shape closure may bake in a CK25-specific vocabulary term --
    re-running the SAME closure against a completely different (synthetic)
    ontology's own IRIs must parse cleanly and reference ONLY the
    synthetic ontology's own namespace (``http://ex.org/``) + the
    well-known ``rdfs:label``, never a CK25 marker string."""
    shape = _shape(shape_name)
    query = shape.build_sparql(_SYNTHETIC_BINDINGS[shape_name])

    assert _canonical(query) is not None, (
        f"{shape_name}: synthetic-ontology build_sparql failed to parse:\n{query}"
    )
    for marker in _CK25_VOCAB_MARKERS:
        assert marker not in query, (
            f"{shape_name}: leaked CK25-specific term {marker!r} on a synthetic ontology:\n{query}"
        )


def test_generate_bank_is_still_a_stub() -> None:
    """Task 1 status check: the pipeline itself is Task 2's job."""
    from tests.nl2sparql.eval.bank_generator import generate_bank

    with pytest.raises(NotImplementedError):
        generate_bank("", "")
