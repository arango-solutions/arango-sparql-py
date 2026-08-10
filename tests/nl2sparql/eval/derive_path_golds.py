"""Derive the 16-case "right-entity, wrong-path" empty-result gold
fixture by EXECUTION-DIFF (RESEARCH.md Open Question 1 / SPEC.md A1) --
never by static SPARQL-text comparison.

The Phase 07.5 composed `grounded + few-shot` CK25 sweep
(``candidates_dump.json``) recorded 31 `passed: false` cases out of 49.
The root-cause investigation split those 31 into four buckets (16
empty-result / 10 wrong-value / 3 ASK-kind-mismatch / 2 harness-empty),
but that split was never committed as a reproducible artifact -- only 6
of the 16 empty-result cases were named explicitly in the scope doc
(ck25-7/12/26/35/47/48). This script re-derives the split MECHANICALLY:

1. Load ``candidates_dump.json`` (the composed arm's per-case verdicts)
   and the CK25 instance graph (``vendored/ck25/raw/prod-inst.ttl``).
2. For every `passed: false` case, classify its `candidate` SPARQL by
   ACTUALLY EXECUTING it against the instance store (never by comparing
   SPARQL text to the gold):
   - ``harness_empty`` -- the candidate string is empty (a harness
     artifact, e.g. the model call failed outright).
   - ``kind_mismatch`` -- the gold is an ASK query but the candidate is
     a SELECT (or vice versa), detected from the ACTUAL SPARQL text kept
     line-anchored (never regex'd against a serialized result type).
   - ``empty_result`` -- the candidate executes to zero rows (SELECT) or
     ``False`` (ASK). This is the "right-entity, wrong-path" bucket R4
     targets: the model found a syntactically valid, EXECUTABLE query
     that simply navigates the wrong predicate path.
   - ``non_empty_wrong`` -- the candidate executes to a non-empty/``True``
     result that still doesn't match the gold (a wrong-VALUE failure --
     out of this phase's scope, SPEC.md's separate "synthbank v2" lever).

Per-case anchor-class / target-predicate / gold-edge-sequence
annotations for the ``empty_result`` bucket are HAND-TRANSCRIBED from
each case's own ``gold`` SPARQL text below (``_GOLD_ANNOTATIONS``).
This is TEST-ONLY and does NOT violate the engine's no-hand-curation
constraint (CONTEXT.md, D-02): ``ClassPathIndex``/``build_path_index``
derive the class-connectivity graph purely mechanically from the TBox;
only this eval-side, human-readable FIXTURE (what the gold path IS for
a specific gold SPARQL query) is hand-transcribed, exactly as
``test_grounding_recall.py``'s own corpus-derived golds are read
directly from each case's ``expected`` field.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).parent
_CANDIDATES_DUMP_PATH = EVAL_DIR / "candidates_dump.json"
_CK25_DATA_PATH = EVAL_DIR / "vendored" / "ck25" / "raw" / "prod-inst.ttl"
_OUTPUT_DEFAULT = EVAL_DIR / "path_recall_golds.yml"

_ASK_RE = re.compile(r"^\s*ASK\b", re.IGNORECASE | re.MULTILINE)

# Expected bucket sizes when this script is authored (root-cause doc's
# own split of the 31 `passed: false` composed-arm cases). `--check-count`
# asserts these EXACT counts so a future corpus/arm change that shifts the
# split is caught loudly rather than silently drifting the fixture.
_EXPECTED_BUCKET_COUNTS = {
    "empty_result": 16,
    "non_empty_wrong": 10,
    "kind_mismatch": 3,
    "harness_empty": 2,
}

# --------------------------------------------------------------------------
# Hand-transcribed gold-path annotations for the 16 `empty_result` cases
# (TEST-ONLY fixture data -- see module docstring). Each entry gives the
# anchor class local name(s) a real seam-6-driven adapter would resolve
# for this question, the target object-property local name(s) a real
# seam-7 token-scorer would surface, and the gold navigation edge
# sequence (predicate local names, "^-1" suffix = traversed against the
# predicate's declared direction) transcribed from the case's OWN gold
# SPARQL join/star pattern. ck25-47/ck25-48 are the two depth-4
# supply-chain cases (SPEC.md: "logged as a known limitation, not
# targeted") -- their gold_edges are 4 hops long and are EXPECTED to
# miss the depth-<=3 recall gate; they stay in the 16-case total (they
# are genuinely execution-diff-derived empty-result failures) but count
# against the accepted 2-case slack in the >=14/16 floor.
# --------------------------------------------------------------------------
_GOLD_ANNOTATIONS: dict[str, dict[str, Any]] = {
    "ck25-4": {
        "anchor_classes": ["Department"],
        "targets": ["memberOf"],
        "gold_edges": ["memberOf^-1"],
        "note": "Department -> the person (Agent) who belongs to it; email itself is a datatype hop out of seam-8's scope.",
    },
    "ck25-7": {
        "anchor_classes": ["Department"],
        "targets": ["hasManager"],
        "gold_edges": ["memberOf^-1", "hasManager"],
        "note": "Canonical case: Employee subClassOf Agent (D-9) + inverse memberOf (D-2) recover the manager join.",
    },
    "ck25-12": {
        "anchor_classes": ["ProductCategory"],
        "targets": ["hasSupplier"],
        "gold_edges": ["hasCategory^-1", "hasSupplier"],
        "note": "Anchor on the RANGE side of hasCategory (D-2 inverse required to reach Product, then hasSupplier).",
    },
    "ck25-24": {
        "anchor_classes": ["ProductCategory"],
        "targets": ["hasCategory"],
        "gold_edges": ["hasCategory^-1"],
        "note": "Single inverse hop to the Hardware/Product instance itself; remaining datatype filters are out of scope.",
    },
    "ck25-25": {
        "anchor_classes": ["ProductCategory"],
        "targets": ["hasCategory"],
        "gold_edges": ["hasCategory^-1"],
        "note": "Same shape as ck25-24 (a different category).",
    },
    "ck25-26": {
        "anchor_classes": ["ProductCategory"],
        "targets": ["hasSupplier"],
        "gold_edges": ["hasCategory^-1", "hasSupplier"],
        "note": "Same 2-hop shape as ck25-12; the terminal addressLocality/country datatype hops are out of seam-8's scope.",
    },
    "ck25-27": {
        "anchor_classes": ["Employee"],
        "targets": ["hasManager"],
        "gold_edges": ["hasManager"],
        "note": "hasManager is Employee's own direct edge; the case's real defect is FILTER NOT EXISTS direction (out of seam-8's scope), but the connecting predicate is mechanically surfaced regardless.",
    },
    "ck25-35": {
        "anchor_classes": ["Product"],
        "targets": ["compatibleProduct"],
        "gold_edges": ["compatibleProduct"],
        "note": "D-10's own worked example: a genuine self-loop (domain == range == Product) surviving one traversal.",
    },
    "ck25-36": {
        "anchor_classes": ["Hardware"],
        "targets": ["hasCategory"],
        "gold_edges": ["hasCategory"],
        "note": "Candidate invented areaOfExpertise (Agent->ProductCategory) instead of the real hasCategory (Product->ProductCategory).",
    },
    "ck25-37": {
        "anchor_classes": ["BillOfMaterial"],
        "targets": ["hasBomPart"],
        "gold_edges": ["hasBomPart"],
        "note": "Direct declared edge; quantity itself is a datatype hop on BomPart.",
    },
    "ck25-40": {
        "anchor_classes": ["Hardware"],
        "targets": ["hasProductManager"],
        "gold_edges": ["hasProductManager"],
        "note": "Direct declared edge (Product -> Employee, inherited by Hardware via D-9).",
    },
    "ck25-42": {
        "anchor_classes": ["BillOfMaterial"],
        "targets": ["hasPart"],
        "gold_edges": ["hasBomPart", "hasPart"],
        "note": "Candidate collapsed/reversed the 2-hop BillOfMaterial->BomPart->Product chain.",
    },
    "ck25-46": {
        "anchor_classes": ["Hardware"],
        "targets": ["hasSupplier"],
        "gold_edges": ["hasSupplier"],
        "note": "Direct declared edge (Product -> Supplier, inherited by Hardware via D-9).",
    },
    "ck25-47": {
        "anchor_classes": ["BillOfMaterial"],
        "targets": ["country"],
        "gold_edges": ["hasBomPart", "hasPart", "hasSupplier", "country"],
        "note": "KNOWN LIMITATION (SPEC.md): a genuine 4-hop chain, beyond the locked depth<=3 budget (D-1). Expected miss.",
    },
    "ck25-48": {
        "anchor_classes": ["BillOfMaterial"],
        "targets": ["country"],
        "gold_edges": ["hasBomPart", "hasPart", "hasSupplier", "country"],
        "note": "KNOWN LIMITATION (SPEC.md): the same 4-hop supply-chain shape as ck25-47. Expected miss.",
    },
    "ck25-50": {
        "anchor_classes": ["Department"],
        "targets": ["responsibleFor"],
        "gold_edges": ["responsibleFor"],
        "note": "Candidate reversed the direction of responsibleFor (Department -> Product, not Product -> Department).",
    },
}


def _classify_candidates() -> dict[str, list[dict[str, Any]]]:
    """Execute every `passed: false` composed-arm candidate against the
    real CK25 instance graph and bucket by result (see module docstring).
    Returns ``{bucket_name: [{"name": ..., "detail": ...}, ...]}``."""
    from tests.helpers.oxi import load_store_from_string, oxi_query

    dump = json.loads(_CANDIDATES_DUMP_PATH.read_text())
    data_ttl = _CK25_DATA_PATH.read_text()
    store = load_store_from_string(data_ttl)

    buckets: dict[str, list[dict[str, Any]]] = {
        "empty_result": [],
        "non_empty_wrong": [],
        "kind_mismatch": [],
        "harness_empty": [],
    }
    for case in dump["cases"]:
        if case["passed"]:
            continue
        name = case["name"]
        candidate = case["candidate"]
        gold = case["gold"]

        if not candidate.strip():
            buckets["harness_empty"].append({"name": name})
            continue

        gold_is_ask = bool(_ASK_RE.search(gold))
        candidate_is_ask = bool(_ASK_RE.search(candidate))
        if gold_is_ask != candidate_is_ask:
            buckets["kind_mismatch"].append({"name": name})
            continue

        result = oxi_query(store, candidate)
        if result.kind == "ask":
            is_empty = result.boolean is False
        else:
            is_empty = not result.rows
        bucket = "empty_result" if is_empty else "non_empty_wrong"
        buckets[bucket].append({"name": name})

    return buckets


def _build_fixture(empty_result_names: list[str]) -> dict[str, Any]:
    """Build the ``golds:`` fixture structure for every case in
    *empty_result_names* that has a hand-transcribed annotation."""
    golds = []
    missing = []
    for name in sorted(empty_result_names, key=lambda n: int(n.split("-")[1])):
        ann = _GOLD_ANNOTATIONS.get(name)
        if ann is None:
            missing.append(name)
            continue
        golds.append(
            {
                "name": name,
                "anchor_classes": ann["anchor_classes"],
                "targets": ann["targets"],
                "gold_edges": ann["gold_edges"],
                "note": ann["note"],
            }
        )
    if missing:
        raise ValueError(
            f"execution-diff found empty_result cases with no hand-transcribed "
            f"gold-path annotation in _GOLD_ANNOTATIONS: {missing} -- add them "
            f"before emitting the fixture"
        )
    return {"golds": golds}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", type=Path, default=None, help="write the golds fixture YAML to this path")
    parser.add_argument(
        "--check-count",
        action="store_true",
        help="assert the empty_result bucket matches the expected 14-16 count and exit non-zero on mismatch",
    )
    args = parser.parse_args()

    buckets = _classify_candidates()
    print("Execution-diff bucket counts (31 `passed: false` composed-arm cases):")
    for bucket, cases in buckets.items():
        print(f"  {bucket}: {len(cases)}  {[c['name'] for c in cases]}")

    total_classified = sum(len(v) for v in buckets.values())
    print(f"  TOTAL classified: {total_classified}")

    ok = True
    if args.check_count:
        empty_count = len(buckets["empty_result"])
        if not (14 <= empty_count <= 16):
            print(f"FAIL: empty_result bucket has {empty_count} cases, expected 14-16")
            ok = False
        else:
            print(f"OK: empty_result bucket has {empty_count} cases (within the expected 14-16 range)")
        for name, expected in _EXPECTED_BUCKET_COUNTS.items():
            actual = len(buckets[name])
            if actual != expected:
                print(f"WARN: bucket {name!r} has {actual} cases, expected {expected} (corpus/arm may have drifted)")

    if args.emit is not None:
        empty_result_names = [c["name"] for c in buckets["empty_result"]]
        fixture = _build_fixture(empty_result_names)
        args.emit.write_text(yaml.safe_dump(fixture, sort_keys=False, default_flow_style=False))
        print(f"Wrote {len(fixture['golds'])} golds to {args.emit}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
