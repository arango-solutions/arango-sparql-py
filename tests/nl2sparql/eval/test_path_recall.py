"""Relationship-path grounding (seam 8, NL-ACC-03): the canonical
end-to-end recovery proof (Task 1). The offline R4 path-recall gate and
the no-ontology-branch static scan (Task 3) extend this file once the
execution-diff-derived gold fixture (Task 2) exists.

Mirrors ``test_grounding_recall.py``'s own discipline exactly: build the
index ONCE from the real CK25 TBox and assert against it. Not marked
``pytest.mark.eval``, no ``RUN_EVAL`` gate — this is deterministic and
touches no LLM/provider.
"""

from __future__ import annotations

from tests.nl2sparql.eval.grounding_index_builder import build_path_index
from tests.nl2sparql.eval.runner import EVAL_DIR, _load_corpus

_CK25_CORPUS_PATH = EVAL_DIR / "vendored" / "ck25" / "corpus.yml"


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
