"""Phase 07.5 Plan 02 (Wave 1) -- unit + offline-gate coverage for
``bank_generator.py``'s 9 real ``ShapeTemplate`` closures and the
``generate_bank``/``generate_bank_with_report`` pipeline.

Two complementary test styles, matching the plan's own two tasks:

- **Task 1** (direct closure tests): hand-crafted ``binding`` dicts
  (never going through the full data-binding pipeline) exercise every
  shape's ``build_sparql`` in isolation -- proving each closure parses,
  never emits an instance-namespace IRI, and carries NO hardcoded
  vocabulary term (re-run against a synthetic, non-CK25 ontology).
- **Task 2** (pipeline tests): the full ``generate_bank_with_report``
  pipeline against the REAL, fixed CK25 vendored ontology + instance
  data -- proving >=7 (target 9) distinct shapes survive the
  execution-non-empty + strict-extremum gates, the per-shape yield
  report accounts for every catalog shape, generation is byte-stable
  under a fixed seed, and the committed
  ``vendored/ck25/generated_fewshot_bank.yml`` matches a fresh
  regeneration + passes the offline ``verify_generated_bank.py`` gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyoxigraph", reason="[dev] extra required for the eval-only oxi helpers")

from tests.nl2sparql.eval.bank_generator import (
    RDFS_LABEL_IRI,
    SHAPE_CATALOG,
    generate_bank,
    generate_bank_with_report,
)
from tests.nl2sparql.eval.runner import _canonical

_CK25_ONTOLOGY_PATH = Path(__file__).parent / "vendored" / "ck25" / "ontology.ttl"
_CK25_DATA_PATH = Path(__file__).parent / "vendored" / "ck25" / "raw" / "prod-inst.ttl"
_CK25_CORPUS_PATH = Path(__file__).parent / "vendored" / "ck25" / "corpus.yml"
_CK25_BANK_PATH = Path(__file__).parent / "vendored" / "ck25" / "generated_fewshot_bank.yml"
_CK25_REPORT_PATH = Path(__file__).parent / "reports" / "generation_report_ck25.json"

_PV = "http://ld.company.org/prod-vocab/"
_PRODI = "http://ld.company.org/prod-instances/"

_SHAPE_NAMES = [t.name for t in SHAPE_CATALOG]


def _shape(name: str):
    return next(t for t in SHAPE_CATALOG if t.name == name)


# --------------------------------------------------------------------------
# Task 1: direct build_sparql closure tests (hand-crafted bindings, no
# data-binding pipeline involved) -- every closure must parse and be
# instance-IRI-free for REAL CK25 IRIs.
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
# Task 1: schema-agnostic proof -- every closure re-run against a SECOND,
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


# --------------------------------------------------------------------------
# Task 2: full generate_bank_with_report pipeline against the REAL, fixed
# CK25 vendored ontology + instance data.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ck25_bank_and_report():
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    data_ttl = _CK25_DATA_PATH.read_text()
    return generate_bank_with_report(ontology_ttl, data_ttl, seed=0)


def test_ck25_bank_has_at_least_seven_distinct_shapes(ck25_bank_and_report) -> None:
    bank, report = ck25_bank_and_report
    kept_shapes = {name for name, r in report.items() if r["kept"] > 0}
    example_shapes = {ex["shape"] for ex in bank["examples"]}

    assert kept_shapes == example_shapes, "report kept-count and emitted examples disagree on shape coverage"
    assert len(kept_shapes) >= 7, (
        f"expected >=7 (target 9) distinct shapes, got {len(kept_shapes)}: {kept_shapes}"
    )


def test_ck25_generation_report_accounts_for_every_catalog_shape(ck25_bank_and_report) -> None:
    _bank, report = ck25_bank_and_report

    assert set(report.keys()) == set(_SHAPE_NAMES), "report must list every one of the 9 catalog shapes"
    for name, stats in report.items():
        assert "kept" in stats and "dropped" in stats and "reasons" in stats
        if stats["kept"] == 0:
            assert stats["reasons"], (
                f"shape {name!r} kept 0 examples with NO logged drop reason "
                "(D-02 / Pitfall 6: a silent 0-yield shape is forbidden)"
            )


def test_ck25_bank_examples_are_valid_and_name_anchored(ck25_bank_and_report) -> None:
    bank, _report = ck25_bank_and_report
    assert len(bank["examples"]) > 0
    for example in bank["examples"]:
        assert _canonical(example["query"]) is not None, f"failed to parse: {example['query']}"
        assert _PRODI not in example["query"], f"instance-namespace IRI leaked: {example['query']}"


def test_ck25_bank_version_and_examples_only_shape() -> None:
    """The bank dict's top-level keys are exactly ``version``/``examples``
    (no ``ontology:`` block -- that would trip the curated-bank-specific
    ``test_bank_ontology_matches_corpus``, per RESEARCH)."""
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    data_ttl = _CK25_DATA_PATH.read_text()
    bank = generate_bank(ontology_ttl, data_ttl, seed=0)

    assert bank["version"] == 1
    assert "ontology" not in bank
    for example in bank["examples"]:
        assert "question" in example and "query" in example


def test_generation_is_byte_stable_under_fixed_seed() -> None:
    """Q7 reproducibility: regenerating with the same seed must be
    byte-stable (identical bank + report)."""
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    data_ttl = _CK25_DATA_PATH.read_text()

    bank1, report1 = generate_bank_with_report(ontology_ttl, data_ttl, seed=0)
    bank2, report2 = generate_bank_with_report(ontology_ttl, data_ttl, seed=0)

    assert bank1 == bank2
    assert report1 == report2


def test_generate_bank_degrades_to_empty_without_instance_data() -> None:
    """D-04: every Stage-1 shape here is data-bound -- without *data_ttl*
    (TBox-only), generation must degrade to an honest empty bank (every
    shape's drop reason recorded), never crash."""
    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    bank, report = generate_bank_with_report(ontology_ttl, data_ttl=None, seed=0)

    assert bank == {"version": 1, "examples": []}
    for name in _SHAPE_NAMES:
        assert report[name]["reasons"], f"shape {name!r} has no TBox-only degrade reason logged"


# --------------------------------------------------------------------------
# Committed-artifact regression: the checked-in
# vendored/ck25/generated_fewshot_bank.yml must match a fresh
# regeneration (no generator/artifact drift) and pass the offline
# validity gate.
# --------------------------------------------------------------------------


def test_committed_ck25_bank_matches_fresh_regeneration() -> None:
    import yaml

    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    data_ttl = _CK25_DATA_PATH.read_text()
    fresh = generate_bank(ontology_ttl, data_ttl, seed=0)

    committed = yaml.safe_load(_CK25_BANK_PATH.read_text())
    assert committed == fresh, "committed generated_fewshot_bank.yml is stale vs. the current generator"


def test_committed_ck25_report_matches_fresh_regeneration() -> None:
    import json

    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    data_ttl = _CK25_DATA_PATH.read_text()
    _bank, fresh_report = generate_bank_with_report(ontology_ttl, data_ttl, seed=0)

    committed = json.loads(_CK25_REPORT_PATH.read_text())
    assert committed["shapes"] == fresh_report, (
        "committed generation_report_ck25.json is stale vs. the current generator"
    )
    assert committed["total_kept"] == sum(r["kept"] for r in fresh_report.values())
    assert committed["total_dropped"] == sum(r["dropped"] for r in fresh_report.values())


def test_offline_validity_gate_green_on_committed_ck25_bank() -> None:
    from tests.nl2sparql.eval.verify_generated_bank import verify_bank

    exit_code = verify_bank(_CK25_BANK_PATH, _CK25_CORPUS_PATH, _CK25_DATA_PATH)
    assert exit_code == 0, "verify_generated_bank.py must exit 0 on the committed CK25 bank"
