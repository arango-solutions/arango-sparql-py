"""WR-03: deterministic unit coverage for `build_label_index`'s own
query/normalization logic, independent of `test_grounding_recall.py`'s
end-to-end gold-IRI *recall* assertion.

The recall test passes today (0.96) even with CR-01 (schema-term leakage)
and CR-02 (corrupted language-tagged labels) both present, because the
real named individuals it checks for still out-rank the schema noise — it
has no assertion on *precision/purity* of what gets indexed, nor on label
cleanliness. This file closes exactly that gap with a small, hand-rolled
Turtle fixture built directly through `build_label_index` (mirroring
`test_grounding_engine_prompt.py`'s `_build_index()` pattern, but exercising
the real SPARQL-query-building/normalization path rather than constructing
a `LabelIndex` by hand):

- schema-IRI exclusion (CR-01): a class/property subject carrying
  `rdfs:label` (whether or not it is explicitly typed `owl:Class`/
  `owl:...Property`) must never appear in the built index.
- label normalization (CR-02): both a language-tagged (`@en`) and a
  datatype-tagged (`^^xsd:string`) label on a real instance must
  normalize to clean text with no stray `"`/`@lang`/`^^` remnants.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyoxigraph", reason="[dev] extra required for the eval-only oxi helpers")

from arango_sparql.nl2sparql.engine_adapter import PREDICATE_DUMP_THRESHOLD
from tests.nl2sparql.eval.grounding_index_builder import (
    build_label_index,
    build_predicate_index,
    build_predicate_signals,
)

_TTL = """
@prefix ex: <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:Person a owl:Class ;
  rdfs:label "Person"@en .

ex:hasName a owl:DatatypeProperty ;
  rdfs:label "has name"@en .

# Deliberately untyped (no owl:Class/owl:...Property) -- these must still
# be excluded by the STRUCTURAL filters (used as an rdf:type object / used
# as a predicate elsewhere), not just the explicit _SCHEMA_TYPES list.
ex:Employee rdfs:label "Employee"@en .
ex:worksAt rdfs:label "works at"@en .

ex:alice a ex:Person ;
  ex:worksAt ex:acme ;
  rdfs:label "Alice Smith"@en .

ex:bob a ex:Employee ;
  rdfs:label "Bob"^^xsd:string .
""".strip()


def _build():
    return build_label_index(_TTL, ["rdfs:label"], prefixes={"ex": "http://ex.org/"})


def test_schema_level_subjects_excluded_from_index() -> None:
    index = _build()
    ids = {e.id for e in index._entities}

    assert "http://ex.org/Person" not in ids, "explicitly-typed owl:Class subject leaked"
    assert "http://ex.org/hasName" not in ids, "explicitly-typed owl:DatatypeProperty subject leaked"
    assert "http://ex.org/Employee" not in ids, (
        "untyped subject used as an rdf:type object leaked (structural filter (b) not applied)"
    )
    assert "http://ex.org/worksAt" not in ids, (
        "untyped subject used as a predicate leaked (structural filter (c) not applied)"
    )


def test_real_instances_retained_with_clean_normalized_labels() -> None:
    index = _build()
    by_id = {e.id: e for e in index._entities}

    assert "http://ex.org/alice" in by_id
    assert "http://ex.org/bob" in by_id

    alice_labels = by_id["http://ex.org/alice"].labels
    bob_labels = by_id["http://ex.org/bob"].labels

    assert alice_labels == ("Alice Smith",), f"language-tagged label not normalized cleanly: {alice_labels!r}"
    assert bob_labels == ("Bob",), f"datatype-tagged label not normalized cleanly: {bob_labels!r}"

    for labels in (alice_labels, bob_labels):
        for label in labels:
            assert '"' not in label, f"stray quote survived normalization: {label!r}"
            assert "^^" not in label, f"stray datatype suffix survived normalization: {label!r}"
            assert "@en" not in label, f"stray language-tag suffix survived normalization: {label!r}"


# --------------------------------------------------------------------------
# Phase 07.4-03: `build_predicate_index()` shape-derivation precision/purity
# tests (RESEARCH.md Wave 0 Gap #1). A small hand-rolled TBox fixture (NOT
# an instance graph) reproducing the four discriminating cases the
# corrected 3-way shape rule was verified against on the real CK25 TBox:
# a value-object-shaped property (range class has ONLY datatype-property
# children), a category-instance-shaped property (range class has ZERO own
# children), the false-positive guard (range class has an ObjectProperty
# child -- must classify as linked_entity, NOT value_object), and a plain
# datatype property (-> literal).
# --------------------------------------------------------------------------

_PREDICATE_TTL = """
@prefix ex: <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:Product a owl:Class ; rdfs:label "Product"@en .
ex:Money a owl:Class ; rdfs:label "Money"@en .
ex:Category a owl:Class ; rdfs:label "Category"@en .
ex:Employee a owl:Class ; rdfs:label "Employee"@en .
ex:Boss a owl:Class ; rdfs:label "Boss"@en .

# value_object case: range class (ex:Money) has ONLY datatype children.
ex:hasCost a owl:ObjectProperty ;
  rdfs:label "has cost"@en ;
  rdfs:domain ex:Product ;
  rdfs:range ex:Money .

ex:amount a owl:DatatypeProperty ;
  rdfs:label "amount"@en ;
  rdfs:domain ex:Money ;
  rdfs:range xsd:decimal .

ex:currency a owl:DatatypeProperty ;
  rdfs:label "currency"@en ;
  rdfs:domain ex:Money ;
  rdfs:range xsd:string .

# category_instance case: range class (ex:Category) has ZERO own children.
ex:hasCategory a owl:ObjectProperty ;
  rdfs:label "has category"@en ;
  rdfs:domain ex:Product ;
  rdfs:range ex:Category .

# linked_entity false-positive guard: range class (ex:Boss) HAS a child,
# but it is an ObjectProperty (ex:hasDirectReport) -- a naive "range class
# has >=1 own property" rule would wrongly flag ex:hasBoss as value_object,
# identical to ex:hasCost above. The corrected rule must NOT do that.
ex:hasBoss a owl:ObjectProperty ;
  rdfs:label "has boss"@en ;
  rdfs:domain ex:Employee ;
  rdfs:range ex:Boss .

ex:hasDirectReport a owl:ObjectProperty ;
  rdfs:label "has direct report"@en ;
  rdfs:domain ex:Boss ;
  rdfs:range ex:Employee .

# literal case: a plain datatype property.
ex:fullName a owl:DatatypeProperty ;
  rdfs:label "full name"@en ;
  rdfs:range xsd:string .
""".strip()


def _build_predicates():
    return build_predicate_index(_PREDICATE_TTL)


def _shape_by_label(index) -> dict[str, str]:
    return {p.label: p.shape for p in index._predicates}


def test_predicate_value_object_shape_derived_for_all_datatype_children() -> None:
    index = _build_predicates()
    shapes = _shape_by_label(index)

    assert shapes["has cost"] == "value_object"

    by_label = {p.label: p for p in index._predicates}
    hop = by_label["has cost"]
    assert hop.shape_detail, "value_object predicate must carry its child (label, range) pairs"
    child_labels = {label for label, _ in hop.shape_detail}
    assert child_labels == {"amount", "currency"}


def test_predicate_category_instance_shape_derived_for_zero_children() -> None:
    index = _build_predicates()
    shapes = _shape_by_label(index)

    assert shapes["has category"] == "category_instance"


def test_predicate_linked_entity_shape_not_misclassified_as_value_object() -> None:
    """The exact false positive RESEARCH.md's Pattern 1 discovered and fixed:
    a range class with an ObjectProperty (not all-datatype) child must
    classify as linked_entity, never value_object."""
    index = _build_predicates()
    shapes = _shape_by_label(index)

    assert shapes["has boss"] == "linked_entity"
    assert shapes["has boss"] != "value_object"


def test_predicate_literal_shape_derived_for_datatype_property() -> None:
    index = _build_predicates()
    shapes = _shape_by_label(index)

    assert shapes["full name"] == "literal"


# --------------------------------------------------------------------------
# Phase 07.4-03 Task 3: QALD DBpedia shape-distribution smoke check.
# Resolves RESEARCH.md Open Question 1 (Assumption A3 guard) -- runs the
# mechanical builder against the real 250-property DBpedia subset (~6x
# PREDICATE_DUMP_THRESHOLD) BEFORE the live QALD sweep, and records the
# actual shape-distribution counts honestly. Per OQ1, a "0 value_object,
# N category_instance" result is a VALID, EXPECTED finding here (DBpedia's
# subset carries no rdfs:domain/rdfs:range/rdfs:label declarations at all --
# verified via direct read/grep -- so every object property's range class
# trivially has zero exact-domain-match children, degrading to
# category_instance; every datatype property -> literal) -- NOT a bug to
# chase. This test intentionally does NOT hard-assert specific per-shape
# counts (only that the retrieve path is exercised on a real, large
# fixture); see 07.4-03-SUMMARY.md for the recorded counts.
# --------------------------------------------------------------------------

_QALD_DBPEDIA_SUBSET_PATH = Path(__file__).parent / "vendored" / "qald9plus" / "dbpedia_subset.ttl"


def test_predicate_qald_dbpedia_subset_shape_distribution_recorded_honestly() -> None:
    ontology_ttl = _QALD_DBPEDIA_SUBSET_PATH.read_text()
    index = build_predicate_index(ontology_ttl)

    predicates = index._predicates
    total = len(predicates)

    # (a) the mechanical builder runs on a real, large DBpedia-style schema
    # and exercises the retrieve (not dump) path -- CK25's 30 predicates
    # dump in full; QALD's 250 sit ~6x over the threshold.
    assert total > 0, "build_predicate_index returned an empty PredicateIndex for the QALD subset"
    assert total > PREDICATE_DUMP_THRESHOLD, (
        f"expected >{PREDICATE_DUMP_THRESHOLD} predicates (retrieve-path fixture), got {total}"
    )

    # (b) compute + record the shape-distribution counts. Deliberately NOT
    # asserted per-shape (OQ1: a 0-value_object DBpedia result is a valid
    # honest finding, not a failure) -- printed so `-s` / CI logs capture
    # the actual distribution, and recorded verbatim in the plan's SUMMARY.
    distribution = {"value_object": 0, "category_instance": 0, "linked_entity": 0, "literal": 0}
    for predicate in predicates:
        distribution[predicate.shape] += 1

    print(f"QALD dbpedia_subset.ttl shape distribution (n={total}): {distribution}")
    assert sum(distribution.values()) == total, "every predicate must classify into exactly one shape"


# --------------------------------------------------------------------------
# Phase 07.5 Wave 0 (D-02): `build_predicate_signals` -- orderable-literal
# + optional-relation walker-extension coverage against the REAL CK25
# vendored TBox (+ instance data), per the plan's confirmed empirical
# values (mechanical, zero per-schema hardcoding in the builder itself).
# --------------------------------------------------------------------------

_CK25_ONTOLOGY_PATH = Path(__file__).parent / "vendored" / "ck25" / "ontology.ttl"
_CK25_DATA_PATH = Path(__file__).parent / "vendored" / "ck25" / "raw" / "prod-inst.ttl"
_PV = "http://ld.company.org/prod-vocab/"

# The seven xsd:decimal predicates confirmed against the real CK25 TBox
# (RESEARCH.md "The 07.4-walker extension (D-02)").
_CK25_ORDERABLE_PREDICATES = {
    f"{_PV}amount",
    f"{_PV}weight_g",
    f"{_PV}height_mm",
    f"{_PV}width_mm",
    f"{_PV}depth_mm",
    f"{_PV}reliabilityIndex",
    f"{_PV}quantity",
}


def test_orderable_true_for_all_seven_ck25_decimal_predicates() -> None:
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    signals = build_predicate_signals(ontology_ttl, _CK25_DATA_PATH.read_text())

    for iri in _CK25_ORDERABLE_PREDICATES:
        assert signals[iri].orderable is True, f"{iri} should be orderable (xsd:decimal range)"


def test_orderable_false_for_xsd_string_predicates() -> None:
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    signals = build_predicate_signals(ontology_ttl, _CK25_DATA_PATH.read_text())

    assert signals[f"{_PV}name"].orderable is False, "pv:name (xsd:string) must not be orderable"
    assert signals[f"{_PV}addressCountry"].orderable is False, (
        "pv:addressCountry (xsd:string) must not be orderable"
    )


def test_optional_relation_is_data_driven_on_prod_inst() -> None:
    """pv:country (domain pv:Supplier) is a genuine optional relation on the
    real CK25 instance data: 227 suppliers carry it, 23 lack it. pv:hasManager
    (domain pv:Employee) is NOT optional: every one of the 47 real Employee
    instances carries it -- confirmed via direct oxi_query probes against
    prod-inst.ttl before writing this test."""
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    signals = build_predicate_signals(ontology_ttl, _CK25_DATA_PATH.read_text())

    assert signals[f"{_PV}country"].optional_relation is True, (
        "pv:country must be flagged optional_relation (some Suppliers lack it)"
    )
    assert signals[f"{_PV}hasManager"].optional_relation is False, (
        "pv:hasManager must NOT be flagged optional_relation (every Employee has one)"
    )


def test_optional_relation_unavailable_false_on_tbox_only() -> None:
    """When data_ttl is None (TBox-only, e.g. QALD), optional_relation must
    degrade to False for every predicate -- never crash."""
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    signals = build_predicate_signals(ontology_ttl, data_ttl=None)

    assert signals[f"{_PV}country"].optional_relation is False
    assert all(not s.optional_relation for s in signals.values()), (
        "every predicate's optional_relation must be False/unavailable with no instance data"
    )
