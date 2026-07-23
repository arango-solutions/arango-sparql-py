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

from tests.nl2sparql.eval.grounding_index_builder import build_label_index
from tests.nl2sparql.eval.runner import EVAL_DIR, _load_corpus

_CK25_CORPUS_PATH = EVAL_DIR / "vendored" / "ck25" / "corpus.yml"
_IRI_RE = re.compile(r"<http://ld\.company\.org/prod-instances/[^>]+>")


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
        f"grounding retrieval recall regressed: {hits}/{total} = {recall:.2f} "
        f"(spike measured 24/25 = 0.96)"
    )
