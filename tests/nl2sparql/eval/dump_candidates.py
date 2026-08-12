"""Diagnostic: dump per-case candidate SPARQL + judge verdict for one arm.

Pass/fail alone can't tell us WHY a case fails. This runs a single config
arm and records, per case: the model's candidate SPARQL, the gold, whether
it passed, and the judge_note — so failures can be root-caused OFFLINE
(no further key spend) into:

  * candidate_engine_rejected  -> the model produced malformed/unsupported
                                  SPARQL (a generation defect)
  * gold_engine_limitation     -> the reference engine can't run the gold
                                  (an eval defect; should be ~0 after the
                                  xsd:int shim)
  * plain False (judge_note None) -> executed fine, WRONG answer set. Split
                                  further offline: near-miss on a big table
                                  vs. structurally wrong vs. ASK-kind
                                  mismatch vs. wrong entity/predicate.

Default arm is the composed ceiling (grounded + generated few-shot). Once
the candidates are captured, the ASK-relaxation and row-level-F1 re-grades
run offline against this dump — no re-run needed.

Modes
-----
--dry-run  (default; NO key)  run the scripted twin, prove the dump wiring.
--dump     (HUMAN-run: RUN_EVAL=1 + NL2SPARQL_API_KEY)  run the live arm and
           write candidates_dump.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.chdir(REPO)
EVAL_DIR = Path(__file__).resolve().parent
RESULT = EVAL_DIR / "candidates_dump.json"

DEFAULT_ARM = "openai-gpt4o-mini-ck25-grounded-generated-fewshot"
SCRIPTED_TWIN = "scripted-ck25-grounded-generated-fewshot"


def _dump(arm: str) -> int:
    from tests.nl2sparql.eval.runner import run

    rep = run(arm)
    records = []
    for c in rep.cases:
        records.append(
            {
                "name": c.name,
                "passed": c.passed,
                "judge_note": c.judge_note,
                "gold": c.expected,
                "candidate": c.actual,
            }
        )
    npass = sum(1 for r in records if r["passed"])
    RESULT.write_text(
        json.dumps({"arm": arm, "n": len(records), "passed": npass, "cases": records}, indent=2) + "\n"
    )

    # quick judge_note histogram over failures (the offline root-cause seed)
    from collections import Counter

    fails = [r for r in records if not r["passed"]]

    def bucket(note):
        if note is None:
            return "wrong-answer (executed, answer set mismatch)"
        if note.startswith("candidate_engine_rejected"):
            return "candidate_engine_rejected (malformed SPARQL)"
        if note.startswith("gold_engine_limitation"):
            return "gold_engine_limitation (eval defect)"
        return note

    hist = Counter(bucket(r["judge_note"]) for r in fails)
    print("=" * 60)
    print(f"arm={arm}  {npass}/{len(records)} passed")
    print(f"failures: {len(fails)}  — judge_note buckets:")
    for k, v in hist.most_common():
        print(f"  {v:2d}  {k}")
    print("=" * 60)
    print(f"Wrote {RESULT} (per-case candidate SPARQL for offline root-cause).")
    return 0


def dry_run() -> int:
    print("DRY RUN — scripted twin, no key: proving the dump wiring records")
    print("candidate + gold + judge_note per case.")
    return _dump(SCRIPTED_TWIN)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="run the live arm + dump candidates (needs key)")
    ap.add_argument("--arm", default=DEFAULT_ARM, help=f"config arm to dump (default: {DEFAULT_ARM})")
    ap.add_argument(
        "--dry-run", action="store_true", help="offline wiring proof via the scripted twin (default)"
    )
    args = ap.parse_args()
    if args.dump:
        if os.getenv("RUN_EVAL", "").strip().lower() in ("", "0", "false", "no"):
            print("ERROR: set RUN_EVAL=1 to run the live dump.", file=sys.stderr)
            return 2
        if not os.getenv("NL2SPARQL_API_KEY"):
            print("ERROR: NL2SPARQL_API_KEY must be set (human-held key).", file=sys.stderr)
            return 2
        return _dump(args.arm)
    return dry_run()


if __name__ == "__main__":
    sys.exit(main())
