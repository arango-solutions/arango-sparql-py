"""Deterministic gold-IRI retrieval-recall regression guard (NL-ACC-01).

Proves the retrieval mechanism the entity-grounding lever depends on stays
intact, offline, in CI -- independent of any live LLM sweep. This is the
highest-value new CI-visible, non-LLM evidence for NL-ACC-01: the
accuracy proof itself is a human-run live sweep, but the retrieval step it
depends on (build_label_index + LabelIndex.retrieve) is fully deterministic
and can be regression-guarded here.

Ported from ``scratchpad/nl-grounding-spike/grounding_spike.py``'s recall
loop (lines ~176-190), which measured 24/25 = 0.96 gold instance-IRI
retrieval recall on CK25's live sweep. This test asserts recall >= 0.90
(the spike floor, with headroom) and runs in the ALWAYS-ON tier (no
``pytest.mark.eval``, no ``RUN_EVAL`` gate) since it is deterministic,
offline, and touches no LLM/provider.
"""

from __future__ import annotations

import re

from tests.nl2sparql.eval.grounding_index_builder import build_label_index, build_predicate_index
from tests.nl2sparql.eval.runner import EVAL_DIR, _load_corpus

_CK25_CORPUS_PATH = EVAL_DIR / "vendored" / "ck25" / "corpus.yml"
_IRI_RE = re.compile(r"<http://ld\.company\.org/prod-instances/[^>]+>")
# Matches any `pv:LocalName` mention in a gold SPARQL query -- this catches
# both predicate usages (`pv:hasManager`) and the occasional class usage
# (`?result a pv:Department`) at face value (D-02: mechanical, no hand-
# curated predicate-vs-class disambiguation here); the measured floor below
# is calibrated against this literal mention set, not a hand-filtered one.
_PREDICATE_RE = re.compile(r"pv:([A-Za-z]+)")


def _local_name(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def test_gold_iri_retrieval_recall_meets_spike_floor() -> None:
    corpus = _load_corpus(_CK25_CORPUS_PATH)
    data_ttl = (_CK25_CORPUS_PATH.parent / corpus["data_path"]).read_text()
    index = build_label_index(data_ttl, ["rdfs:label", "pv:name"])

    hits = total = 0
    for case in corpus["cases"]:
        gold_iris = set(_IRI_RE.findall(case["expected"]))
        if not gold_iris:
            continue
        retrieved = {f"<{e.id}>" for e in index.retrieve(case["nl"], k=20)}
        hits += len(gold_iris & retrieved)
        total += len(gold_iris)

    assert total > 0, "no CK25 case named a gold instance IRI -- recall guard would be vacuous"
    recall = hits / total
    assert recall >= 0.90, (
        f"grounding retrieval recall regressed: {hits}/{total} = {recall:.2f} (spike measured 24/25 = 0.96)"
    )


def test_predicate_retrieval_recall_meets_mechanical_builder_floor() -> None:
    """Deterministic gold-predicate retrieval-recall regression guard (seam 7).

    Sibling of the entity-recall guard above, offline and always-on (no
    ``RUN_EVAL``/``pytest.mark.eval``): builds a ``PredicateIndex`` from
    CK25's TBox (``shared_ontology`` -- via ``build_predicate_index``, NOT
    the instance graph ``build_label_index`` above consumes) and measures how
    often ``PredicateIndex.retrieve(case["nl"], k=40)`` (``k=40`` mirrors this
    corpus's ``predicate_grounding: {k: 40}`` config entry, CK25's 30
    properties sit under ``PREDICATE_DUMP_THRESHOLD``) surfaces every
    ``pv:LocalName`` mentioned in that case's gold SPARQL.

    Measured: 78/158 = 0.49 (recorded honestly in 07.4-04-SUMMARY.md, not an
    aspirational number) -- lower than the entity guard's 0.96 because the
    literal ``pv:[A-Za-z]+`` scan also counts occasional class mentions
    (e.g. ``?result a pv:Department``) that a predicate-only index can never
    retrieve, and because the token-substring scorer is a bag-of-words match
    over a short NL question, not a semantic one. The floor is set BELOW the
    measured value (headroom), never above it.
    """
    corpus = _load_corpus(_CK25_CORPUS_PATH)
    index = build_predicate_index(corpus["ontology"])

    hits = total = 0
    for case in corpus["cases"]:
        gold_names = set(_PREDICATE_RE.findall(case["expected"]))
        if not gold_names:
            continue
        retrieved = {_local_name(p.iri) for p in index.retrieve(case["nl"], k=40)}
        hits += len(gold_names & retrieved)
        total += len(gold_names)

    assert total > 0, "no CK25 case named a gold pv: predicate -- recall guard would be vacuous"
    recall = hits / total
    assert recall >= 0.45, (
        f"predicate retrieval recall regressed: {hits}/{total} = {recall:.2f} "
        f"(measured 78/158 = 0.49 when this guard was authored)"
    )
