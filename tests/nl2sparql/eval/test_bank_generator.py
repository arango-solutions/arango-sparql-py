"""Phase 07.5 Plan 02 (Wave 1) + Plan 03 (Wave 2) -- unit + offline-gate
coverage for ``bank_generator.py``'s 9 real ``ShapeTemplate`` closures,
the ``generate_bank``/``generate_bank_with_report`` pipeline, and (Plan 03)
``paraphrase()``/``slot_preserving()``.

Three complementary test styles, matching the plan's own tasks:

- **Task 1 (Plan 02)** (direct closure tests): hand-crafted ``binding``
  dicts (never going through the full data-binding pipeline) exercise
  every shape's ``build_sparql`` in isolation -- proving each closure
  parses, never emits an instance-namespace IRI, and carries NO hardcoded
  vocabulary term (re-run against a synthetic, non-CK25 ontology).
- **Task 2 (Plan 02)** (pipeline tests): the full
  ``generate_bank_with_report`` pipeline against the REAL, fixed CK25
  vendored ontology + instance data -- proving >=7 (target 9) distinct
  shapes survive the execution-non-empty + strict-extremum gates, the
  per-shape yield report accounts for every catalog shape, generation is
  byte-stable under a fixed seed, and the committed
  ``vendored/ck25/generated_fewshot_bank.yml`` matches a fresh
  regeneration + passes the offline ``verify_generated_bank.py`` gate.
- **Task 2 (Plan 03)** (``*paraphrase_faithful*`` tests, offline/scripted,
  no key, no network): the PRIMARY D-03 faithfulness guard
  (``slot_preserving``) accepts a faithful paraphrase and rejects both a
  slot-dropping and an intent-flipping one; ``paraphrase()`` fed a
  ``ScriptedLLMClient`` returning a mix of faithful/unfaithful candidates
  keeps only the guard-passing ones; and the CK25 bank re-emitted with a
  deterministic offline ``_EchoParaphraseClient`` (SCRIPTED/PLACEHOLDER
  provenance -- see that class's docstring and the bank file's own header
  comment) carries >=3 paraphrases per example and still passes
  ``verify_generated_bank.py`` (paraphrases never change the query, so
  REQ-1/REQ-2 parse+transpile+execute-non-empty stay unaffected). This
  committed bank's paraphrases are SUPERSEDED by Plan 05's real-paraphrase
  regeneration against the live ``OpenAICompatibleClient`` (human-held
  ``NL2SPARQL_API_KEY``) before any REQ-4/REQ-6 measurement; the secondary
  >=20-pair LLM-judge faithfulness audit (REQ-3's credentialed half) is
  also human-run in Plan 05.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyoxigraph", reason="[dev] extra required for the eval-only oxi helpers")

from arango_sparql.nl2sparql.client import ScriptedLLMClient
from arango_sparql.nl2sparql.models import LLMResponse
from tests.nl2sparql.eval.bank_generator import (
    RDFS_LABEL_IRI,
    SHAPE_CATALOG,
    generate_bank,
    generate_bank_with_report,
    paraphrase,
    slot_preserving,
)
from tests.nl2sparql.eval.runner import _canonical

_CK25_ONTOLOGY_PATH = Path(__file__).parent / "vendored" / "ck25" / "ontology.ttl"
_CK25_DATA_PATH = Path(__file__).parent / "vendored" / "ck25" / "raw" / "prod-inst.ttl"
_CK25_CORPUS_PATH = Path(__file__).parent / "vendored" / "ck25" / "corpus.yml"
_CK25_BANK_PATH = Path(__file__).parent / "vendored" / "ck25" / "generated_fewshot_bank.yml"
_CK25_REPORT_PATH = Path(__file__).parent / "reports" / "generation_report_ck25.json"

# Plan 04 (Wave 3, D-04): QALD has no dedicated ``ontology.ttl`` sibling file
# (unlike CK25) -- its TBox lives in ``corpus.yml``'s own ``ontology:`` block
# (verified byte-identical to ``dbpedia_subset.ttl`` -- both are the same
# text, ``corpus.yml`` is simply the canonical eval-harness-consumed copy).
# QALD has NO instance-data Turtle at all (0 instance triples, D-04: no
# DBpedia snapshot is ever built from gold-query entities).
_QALD_CORPUS_PATH = Path(__file__).parent / "vendored" / "qald9plus" / "corpus.yml"
_QALD_BANK_PATH = Path(__file__).parent / "vendored" / "qald9plus" / "generated_fewshot_bank.yml"
_QALD_REPORT_PATH = Path(__file__).parent / "reports" / "generation_report_qald9plus.json"


def _load_qald_ontology() -> str:
    import yaml

    corpus = yaml.safe_load(_QALD_CORPUS_PATH.read_text())
    return corpus["ontology"]


_PV = "http://ld.company.org/prod-vocab/"
_PRODI = "http://ld.company.org/prod-instances/"

_SHAPE_NAMES = [t.name for t in SHAPE_CATALOG]


class _EchoParaphraseClient:
    """Deterministic, OFFLINE, SCRIPTED/PLACEHOLDER paraphrase double
    (Plan 03 D-03) -- NOT a real LLM, no key, no network.

    Echoes the input question back wrapped in one of a small rotating set
    of fixed prefixes. Because the original question text is preserved
    verbatim (only wrapped, never altered), every literal filler and
    intent-lexicon token the PRIMARY ``slot_preserving`` guard checks for
    survives by construction -- giving :func:`paraphrase` >=3
    guard-passing "paraphrases" per example with zero LLM calls, so the
    committed CK25 bank (regenerated with this double) can carry a real
    ``paraphrases`` list while staying fully offline/reproducible.

    Satisfies the ``LLMClient`` duck-typing protocol (``provider``/
    ``model`` attributes + ``generate(messages) -> LLMResponse``) so it
    drops straight into ``generate_bank(..., client=...)`` exactly like a
    real client would. These are PLACEHOLDER paraphrases only -- SUPERSEDED
    by Plan 05's real-paraphrase regeneration against the live,
    human-held-key ``OpenAICompatibleClient`` before any REQ-4/REQ-6
    measurement is taken from this bank.
    """

    _PREFIXES = (
        "Could you tell me: {q}",
        "I would like to know: {q}",
        "Please answer this: {q}",
        "As a follow-up: {q}",
    )

    provider = "scripted"
    model = "placeholder-echo"

    def __init__(self) -> None:
        self._counter = 0

    def generate(self, messages: list[dict[str, str]]) -> LLMResponse:
        question = messages[-1]["content"]
        prefix = self._PREFIXES[self._counter % len(self._PREFIXES)]
        self._counter += 1
        return LLMResponse(content=prefix.format(q=question))


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
    # Plan 03: the committed bank now carries SCRIPTED/PLACEHOLDER
    # paraphrases (see _EchoParaphraseClient's docstring) -- a fresh
    # instance reproduces them byte-stably (deterministic call order).
    fresh = generate_bank(ontology_ttl, data_ttl, seed=0, client=_EchoParaphraseClient(), k_paraphrases=3)

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


# --------------------------------------------------------------------------
# Plan 03 Task 2: offline scripted ``paraphrase``/``slot_preserving``
# faithfulness tests (D-03's PRIMARY guard) -- no RUN_EVAL, no key, no
# network. Every test name below contains ``paraphrase_faithful`` so
# ``pytest -k paraphrase_faithful`` (the plan's own verify command)
# selects all of them.
# --------------------------------------------------------------------------

_CATEGORY_FILTER_BINDING = {
    "range_iri": f"{_PV}ProductCategory",
    "predicate_iri": f"{_PV}hasCategory",
    "filler_label": "Crystal",
}
_SCALAR_COUNT_BINDING = {
    "range_iri": f"{_PV}ProductCategory",
    "predicate_iri": f"{_PV}hasCategory",
    "filler_label": "Crystal",
}
_TOP_N_BINDING = {"domain_iri": f"{_PV}Hardware", "predicate_iri": f"{_PV}amount"}


def test_paraphrase_faithful_slot_preservation() -> None:
    """The PRIMARY guard (``slot_preserving``, pure/offline/deterministic,
    no client/generate call anywhere in it -- see the module-level grep
    gate) accepts a faithful paraphrase and rejects both a slot-dropping
    and an intent-flipping one, per the plan's own three worked cases."""
    category_filter = _shape("category_filter")

    # (1) A faithful scripted paraphrase (preserves the filler + intent) passes.
    faithful = "What products belong to the Crystal category?"
    assert slot_preserving(faithful, category_filter, _CATEGORY_FILTER_BINDING)

    # (2) A slot-dropping scripted paraphrase (drops the category filler) is rejected.
    slot_dropping = "What products are in that category?"
    assert not slot_preserving(slot_dropping, category_filter, _CATEGORY_FILTER_BINDING)

    # (3) An intent-flipping scripted paraphrase (superlative -> "cheapest" on
    # a "most expensive"/top_n template) is rejected; the faithful sibling
    # phrasing (same direction, different superlative synonym) still passes.
    top_n = _shape("top_n")
    faithful_ranking = "Which Hardware item has the most expensive amount?"
    flipped_ranking = "Which Hardware item has the cheapest amount?"
    assert slot_preserving(faithful_ranking, top_n, _TOP_N_BINDING)
    assert not slot_preserving(flipped_ranking, top_n, _TOP_N_BINDING)

    # scalar_count's own intent lexicon ("how many"/"number of"/"count") is
    # a plain-text check (no direction concept) -- dropping it is rejected.
    scalar_count = _shape("scalar_count")
    faithful_count = "How many products are there for the Crystal category?"
    no_intent = "Tell me about products in the Crystal category."
    assert slot_preserving(faithful_count, scalar_count, _SCALAR_COUNT_BINDING)
    assert not slot_preserving(no_intent, scalar_count, _SCALAR_COUNT_BINDING)


def test_paraphrase_faithful_filters_scripted_candidates() -> None:
    """``paraphrase()`` fed a ``ScriptedLLMClient`` returning a mix of
    faithful + unfaithful candidates keeps ONLY the guard-passing ones,
    and >=3 survive (the plan's own K target)."""
    category_filter = _shape("category_filter")
    question = "Which Product are in the Crystal category?"
    responses = [
        LLMResponse(content="Which items fall under the Crystal category?"),  # faithful
        LLMResponse(content="Which items are in that category?"),  # drops filler -- rejected
        LLMResponse(content="What is in the Crystal group?"),  # faithful
        LLMResponse(content="List the Crystal-category members."),  # faithful
    ]
    client = ScriptedLLMClient(responses, latency_ms=0)

    result = paraphrase(question, category_filter, _CATEGORY_FILTER_BINDING, k=3, client=client)

    assert len(result) >= 3
    for candidate in result:
        assert slot_preserving(candidate, category_filter, _CATEGORY_FILTER_BINDING)
    # The rejected slot-dropping candidate must never appear in the output.
    assert "Which items are in that category?" not in result


def test_paraphrase_faithful_degrades_to_empty_without_client_or_key(monkeypatch) -> None:
    """No client injected AND no ``NL2SPARQL_API_KEY`` configured -> an
    honest empty list (never a live call, never a crash) -- D-03's
    documented degrade path."""
    monkeypatch.delenv("NL2SPARQL_API_KEY", raising=False)
    category_filter = _shape("category_filter")
    question = "Which Product are in the Crystal category?"

    result = paraphrase(question, category_filter, _CATEGORY_FILTER_BINDING)

    assert result == []


def test_paraphrase_faithful_reemitted_ck25_bank() -> None:
    """The CK25 bank re-emitted with the offline, deterministic
    ``_EchoParaphraseClient`` (SCRIPTED/PLACEHOLDER provenance) carries
    >=3 paraphrases per example and still passes the offline validity
    gate -- paraphrases never change ``query``, so REQ-1/REQ-2
    (parse+transpile+execute-non-empty) stay unaffected."""
    import yaml

    from tests.nl2sparql.eval.verify_generated_bank import verify_bank

    ontology_ttl = _CK25_ONTOLOGY_PATH.read_text()
    data_ttl = _CK25_DATA_PATH.read_text()
    bank = generate_bank(ontology_ttl, data_ttl, seed=0, client=_EchoParaphraseClient(), k_paraphrases=3)

    assert len(bank["examples"]) > 0
    for example in bank["examples"]:
        paraphrases = example.get("paraphrases", [])
        assert len(paraphrases) >= 3, (
            f"expected >=3 paraphrases, got {len(paraphrases)}: {example['question']!r}"
        )
        # _EchoParaphraseClient wraps the ORIGINAL templated question
        # verbatim behind a fixed prefix -- every literal filler and
        # intent-lexicon token the guard would check is therefore
        # preserved by construction; assert that verbatim-preservation
        # invariant directly here (a stronger, human-inspectable check
        # than re-deriving the shape's own binding, which the emitted
        # bank does not persist).
        for candidate in paraphrases:
            assert example["question"] in candidate, (
                f"echo paraphrase dropped the original question text: {candidate!r}"
            )

    # Matches the committed artifact exactly (see
    # test_committed_ck25_bank_matches_fresh_regeneration) and still
    # passes the same offline validity gate as the paraphrase-free bank.
    committed = yaml.safe_load(_CK25_BANK_PATH.read_text())
    assert committed == bank
    exit_code = verify_bank(_CK25_BANK_PATH, _CK25_CORPUS_PATH, _CK25_DATA_PATH)
    assert exit_code == 0, "verify_generated_bank.py must exit 0 on the re-emitted, paraphrase-bearing bank"


# --------------------------------------------------------------------------
# Plan 04 (Wave 3, D-04/REQ-5): the SAME ``generate_bank``/
# ``generate_bank_with_report`` pipeline, called UNMODIFIED (no QALD-
# specific argument or branch), run against QALD's shallow, TBox-only
# DBpedia subset (75 classes, 250 properties, 0 instance triples, 0
# rdfs:domain/rdfs:range declarations -- 07.4-03). This TBox has no
# instance-level ``rdfs:label`` at all, so EVERY Stage-1 shape here (not
# only the 3 data-driven ones anticipated in RESEARCH -- negation, top_n,
# offset) is unable to sample a real name-anchor filler and self-drops --
# an honest, stronger-than-anticipated confirmation of the SAME degrade
# path ``test_generate_bank_degrades_to_empty_without_instance_data``
# already proves for CK25's own ontology with ``data_ttl=None``: this
# generator's Stage-1 pipeline is universally instance-data-bound BY
# DESIGN, not a QALD-specific gap. The generalization claim this
# supports is "the SAME generator RUNS unmodified and emits a
# structurally-valid bank" (D-04) -- never "lifts QALD".
# --------------------------------------------------------------------------


def test_qald_bank_degrades_to_empty_via_same_pipeline() -> None:
    """REQ-5: calling ``generate_bank_with_report`` on QALD's own TBox with
    ``data_ttl=None`` -- the exact same call shape as the CK25 TBox-only
    proof above, no QALD-specific argument or branch -- degrades to the
    same honest empty bank, with every one of the 9 catalog shapes
    carrying a logged drop reason (D-02 Pitfall 6: no silent gap)."""
    ontology_ttl = _load_qald_ontology()
    bank, report = generate_bank_with_report(ontology_ttl, data_ttl=None, seed=0)

    assert bank == {"version": 1, "examples": []}
    for name in _SHAPE_NAMES:
        assert report[name]["reasons"], f"shape {name!r} has no TBox-only degrade reason logged"


def test_committed_qald_bank_matches_fresh_regeneration() -> None:
    import yaml

    ontology_ttl = _load_qald_ontology()
    fresh = generate_bank(ontology_ttl, data_ttl=None, seed=0)

    committed = yaml.safe_load(_QALD_BANK_PATH.read_text())
    assert committed == fresh, "committed QALD generated_fewshot_bank.yml is stale vs. the current generator"


def test_committed_qald_report_matches_fresh_regeneration() -> None:
    import json

    ontology_ttl = _load_qald_ontology()
    _bank, fresh_report = generate_bank_with_report(ontology_ttl, data_ttl=None, seed=0)

    committed = json.loads(_QALD_REPORT_PATH.read_text())
    assert committed["shapes"] == fresh_report, (
        "committed generation_report_qald9plus.json is stale vs. the current generator"
    )
    assert committed["total_kept"] == sum(r["kept"] for r in fresh_report.values())
    assert committed["total_dropped"] == sum(r["dropped"] for r in fresh_report.values())


def test_offline_validity_gate_green_on_committed_qald_bank() -> None:
    """Structural-only mode (D-04, ``data_path=None``): trivially green on
    a zero-example bank, but exercises the SAME code path as the CK25 gate
    (``verify_bank``, no QALD-specific branch)."""
    from tests.nl2sparql.eval.verify_generated_bank import verify_bank

    exit_code = verify_bank(_QALD_BANK_PATH, _QALD_CORPUS_PATH)
    assert exit_code == 0, "verify_generated_bank.py must exit 0 (structural mode) on the committed QALD bank"

