"""Relationship-path grounding (seam 8, NL-ACC-03): the canonical
end-to-end recovery proof (Task 1) and the offline R4 path-recall gate
(Task 3) — deterministic, always-on, no key, no LLM.

Mirrors ``test_grounding_recall.py``'s own discipline exactly: build the
index ONCE from the real CK25 TBox, compare retrieved-vs-gold, assert a
floor BELOW the measured value. Not marked ``pytest.mark.eval``, no
``RUN_EVAL`` gate — this is deterministic and touches no LLM/provider.
"""

from __future__ import annotations

from tests.nl2sparql.eval.grounding_index_builder import build_path_index
from tests.nl2sparql.eval.runner import EVAL_DIR, _load_corpus

_CK25_CORPUS_PATH = EVAL_DIR / "vendored" / "ck25" / "corpus.yml"
_PATH_GOLDS_PATH = EVAL_DIR / "path_recall_golds.yml"


def _load_golds() -> list[dict]:
    import yaml

    fixture = yaml.safe_load(_PATH_GOLDS_PATH.read_text())
    return fixture["golds"]


def test_canonical_inverse_join_recovered() -> None:
    """R1 acceptance criterion (end-to-end, Task 1): build_path_index over
    the REAL CK25 corpus ontology recovers the canonical ck25-7 "manager
    of the Data Services department" inverse-join — the person-scoped
    ``memberOf``-inverse into an Employee/Agent, then ``hasManager`` —
    among ``shortest_paths(...)``'s <=5 returned paths. Proves D-9
    (subclass-aware nodes: Employee subClassOf Agent) + D-2 (inverse
    edges) working together from the real TBox, before any adapter/eval
    wiring exists (D-01).
    """
    corpus = _load_corpus(_CK25_CORPUS_PATH)
    index = build_path_index(corpus["ontology"])

    paths = index.shortest_paths(["Department"], ["hasManager"], k=5)
    edge_sequences = [p.edges for p in paths]

    assert ("memberOf^-1", "hasManager") in edge_sequences, (
        f"canonical inverse-join not recovered among the top-5 paths: {edge_sequences}"
    )
    # R1 acceptance: at most 5 paths, each of length <= 3 (D-1/D-5).
    assert len(paths) <= 5
    assert all(p.length <= 3 for p in paths)


def test_path_recall_meets_spike_floor() -> None:
    """R4: offline path-recall >= 14/16 on the execution-diff-derived
    empty-result golds (``path_recall_golds.yml``, Task 2) at depth-3
    with subclass-aware nodes + inverse edges + bounded self-revisit.
    "Recovered" = the gold navigation-edge sequence appears among the
    <=5 paths ``shortest_paths(...)`` returns for that gold's own
    (anchor_classes, targets).

    The scope-doc Step-0 recall spike measured ~16/16 at depth-3; the
    floor here (14/16) matches SPEC.md's own R4 acceptance criterion and
    deliberately accepts EXACTLY the two depth-4 supply-chain misses
    (ck25-47/ck25-48, SPEC.md: "logged as a known limitation, not
    targeted") as headroom — this asserts recall is at least that good,
    never that it is perfect.
    """
    corpus = _load_corpus(_CK25_CORPUS_PATH)
    index = build_path_index(corpus["ontology"])
    golds = _load_golds()

    assert 14 <= len(golds) <= 16, (
        f"path_recall_golds.yml has {len(golds)} golds -- recall guard would be "
        f"vacuous or miscalibrated outside the expected 14-16 range"
    )

    misses: list[str] = []
    for gold in golds:
        paths = index.shortest_paths(gold["anchor_classes"], gold["targets"], k=5)
        edge_sequences = [p.edges for p in paths]
        if tuple(gold["gold_edges"]) not in edge_sequences:
            misses.append(gold["name"])

    hits = len(golds) - len(misses)
    total = len(golds)
    recall_floor = 14
    assert hits >= recall_floor, (
        f"path recall regressed: {hits}/{total} recovered (missed: {misses}), "
        f"expected >= {recall_floor}/{total} (spike measured ~16/16 at depth-3)"
    )


def test_no_ontology_branch_in_build_path_index() -> None:
    """R1/D-02 (mirrors ``test_generator_no_ontology_branch``): the
    mechanical TBox-walker ``build_path_index`` carries NO hardcoded
    CK25- or DBpedia-specific vocabulary term/branch in its own function
    source (comments stripped, so historical-fix prose mentioning a term
    BY NAME elsewhere in the module is never a false positive — the scan
    is scoped to ``build_path_index`` itself, not the whole module, since
    sibling functions in this file legitimately discuss CK25 terms in
    their own docstrings)."""
    import inspect

    from tests.nl2sparql.eval.test_bank_generator import _FORBIDDEN_ONTOLOGY_TERMS, _strip_comments

    source = inspect.getsource(build_path_index)
    code_only = _strip_comments(source)
    for term in _FORBIDDEN_ONTOLOGY_TERMS:
        assert term not in code_only, (
            f"build_path_index bakes the ontology-specific vocabulary term {term!r} "
            "into its walker logic -- D-02 forbids any per-schema hint or branch here"
        )
