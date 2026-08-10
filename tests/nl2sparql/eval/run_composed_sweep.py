"""Composed-lever CK25 evaluation (2026-08) — the "real evaluation".

Every NL->SPARQL lever was previously measured only IN ISOLATION and in
DIFFERENT sessions (entity grounding 14/49, few-shot 11-14/49, predicate
grounding 7/49). This harness runs them AND their compositions **in one
session** over the same 49 held-out CK25 cases, so every pairwise
comparison is clean (Pitfall 7: never compare across sessions — gpt-4o-mini
is nondeterministic and drifts). It answers the question the isolated arms
cannot: **do the confirmed levers STACK, and what is the real ceiling of
the system we have already built?**

Arms (same session, gpt-4o-mini @ temp per provider default, judge=execution):
  zero      openai-gpt4o-mini-ck25                             (no seams)
  ground    openai-gpt4o-mini-ck25-grounded                    (seam 6 entity)
  fewshot   openai-gpt4o-mini-ck25-generated-fewshot           (query-first bank)
  g+f       openai-gpt4o-mini-ck25-grounded-generated-fewshot  (the two confirmed levers)
  all       openai-gpt4o-mini-ck25-all-levers                  (+ seam 7 predicate)
  g+f+path  openai-gpt4o-mini-ck25-grounded-generated-fewshot-path (+ seam 8 relationship-path, Phase 07.6)

Reports, for the key contrasts, paired McNemar (b=gains, c=regressions) +
a bootstrap CI on the pass-rate delta:
  * each lever/composition vs the SAME-SESSION fresh zero arm
  * g+f vs ground and g+f vs fewshot  -> the STACKING question
  * all vs g+f                         -> does predicate grounding help or
                                          distract once few-shot is present?
  * g+f+path vs g+f                    -> does the relationship-path hint
                                          help once grounding+few-shot are
                                          present?

Two modes
---------
--dry-run   (default; NO key, NO network)
    Runs the scripted plumbing twins to prove the composed configs build all
    four seams (grounding + predicate + few_shot + path indices) into one
    NlPipeline without crashing.

--sweep     (HUMAN-run: RUN_EVAL=1 + NL2SPARQL_API_KEY)
    Runs all 6 live arms back-to-back in one session, prints the pass table +
    the paired-McNemar matrix, and writes composed_sweep_result.json.
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
RESULT = EVAL_DIR / "composed_sweep_result.json"

# (label, live arm, scripted plumbing twin)
ARMS = [
    ("zero", "openai-gpt4o-mini-ck25", "scripted-ck25"),
    ("ground", "openai-gpt4o-mini-ck25-grounded", "scripted-ck25-grounded"),
    ("fewshot", "openai-gpt4o-mini-ck25-generated-fewshot", "scripted-ck25-generated-fewshot"),
    ("g+f", "openai-gpt4o-mini-ck25-grounded-generated-fewshot", "scripted-ck25-grounded-generated-fewshot"),
    ("all", "openai-gpt4o-mini-ck25-all-levers", "scripted-ck25-all-levers"),
    (
        "g+f+path",
        "openai-gpt4o-mini-ck25-grounded-generated-fewshot-path",
        "scripted-ck25-grounded-generated-fewshot-path",
    ),
]

# Contrasts to report: (name, baseline_label, treatment_label)
CONTRASTS = [
    ("ground vs zero", "zero", "ground"),
    ("fewshot vs zero", "zero", "fewshot"),
    ("g+f vs zero", "zero", "g+f"),
    ("all vs zero", "zero", "all"),
    ("g+f vs ground  (does few-shot add to grounding?)", "ground", "g+f"),
    ("g+f vs fewshot (does grounding add to few-shot?)", "fewshot", "g+f"),
    ("all vs g+f     (does predicate grounding help/distract?)", "g+f", "all"),
    ("g+f+path vs g+f (does the path hint help?)", "g+f", "g+f+path"),
]


def dry_run() -> int:
    from tests.nl2sparql.eval.runner import run

    print("=" * 68)
    print("DRY RUN — no LLM, no network. Proving the composed configs build")
    print("all seams (grounding + predicate + few_shot + path) into one NlPipeline.")
    print("=" * 68)
    for _label, _live, scripted in ARMS:
        r = run(scripted)
        passed = sum(1 for c in r.cases if c.passed)
        print(f"  {scripted:42s} {passed}/{len(r.cases)} (plumbing, no crash)")
    print("\nDRY RUN OK — every composed config builds + threads its seams.")
    return 0


def sweep() -> int:
    if os.getenv("RUN_EVAL", "").strip().lower() in ("", "0", "false", "no"):
        print("ERROR: set RUN_EVAL=1 to run the live sweep.", file=sys.stderr)
        return 2
    if not os.getenv("NL2SPARQL_API_KEY"):
        print("ERROR: NL2SPARQL_API_KEY must be set (human-held key).", file=sys.stderr)
        return 2

    from tests.nl2sparql.eval.runner import (
        bootstrap_paired_delta,
        cached_few_shot_index,
        paired_mcnemar,
        run,
    )

    results: dict[str, dict[str, bool]] = {}
    for label, live, _scripted in ARMS:
        print(f"Running arm '{label}' ({live}) ...")
        cached_few_shot_index.cache_clear()  # rebuild indices per arm (Pitfall 3)
        rep = run(live)
        results[label] = {c.name: c.passed for c in rep.cases}

    npass = {lab: sum(d.values()) for lab, d in results.items()}
    n = len(next(iter(results.values())))

    print("\n" + "=" * 68)
    print(f"  CK25 composed-lever evaluation — same session, n={n}, gpt-4o-mini")
    print("=" * 68)
    print("  Pass counts:")
    for label, _live, _s in ARMS:
        print(f"    {label:8s} {npass[label]:2d}/{n}  ({npass[label] / n:.3f})")

    print("\n  Paired contrasts (b=gains, c=regressions, treatment vs baseline):")
    contrast_rows = []
    for name, base, treat in CONTRASTS:
        b, c, p = paired_mcnemar(results[base], results[treat])
        delta, lo, hi = bootstrap_paired_delta(results[base], results[treat])
        print(f"    {name:52s} b={b:2d} c={c:2d} p={p:.4f}  Δ={delta:+.4f} [{lo:+.4f},{hi:+.4f}]")
        contrast_rows.append({
            "contrast": name, "baseline": base, "treatment": treat,
            "b_gains": b, "c_regressions": c, "p_value": p,
            "delta": delta, "ci_95": [lo, hi],
        })
    print("=" * 68)

    RESULT.write_text(json.dumps({
        "eval": "composed-lever CK25 real-evaluation (2026-08)",
        "model": "gpt-4o-mini", "judge": "execution", "n_cases": n,
        "arms": {lab: live for lab, live, _ in ARMS},
        "pass_counts": npass,
        "contrasts": contrast_rows,
        "per_case": results,
    }, indent=2) + "\n")
    print(f"\nWrote {RESULT}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="run the live multi-arm sweep (needs key)")
    ap.add_argument("--dry-run", action="store_true", help="offline plumbing proof (default)")
    args = ap.parse_args()
    sys.exit(sweep() if args.sweep else dry_run())
