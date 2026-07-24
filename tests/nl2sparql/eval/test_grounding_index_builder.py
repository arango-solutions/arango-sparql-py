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

import pytest

pytest.importorskip("pyoxigraph", reason="[dev] extra required for the eval-only oxi helpers")

from tests.nl2sparql.eval.grounding_index_builder import build_label_index

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
