"""Phase 07.5 Plan 05 sweep runner — D-05/REQ-4/REQ-6: does the GENERATED
(query-first synthetic) CK25 few-shot bank reproduce Spike 001's directional
lift on the held-out corpus, mechanistically (drop-in BM25 proof) and
directionally (credentialed paired sweep), overlap-audited on both the
shape and entity axes?

Mirrors ``.planning/spikes/001-ck25-thin-fewshot-signal/run_spike.py``
structurally. Unlike the spike, this harness needs NO monkeypatch
isolation: Plan 05 Task 2 added the generated-bank arms as ADDITIVE,
committed ``configs.yml`` entries (``openai-gpt4o-mini-ck25-generated-
fewshot`` / ``openai-gpt4o-mini-qald9plus-generated-fewshot`` / their
``scripted-*`` plumbing twins) plus an additive ``few_shot.bank:`` config
sub-key in ``runner.py`` — ``run(config_name)`` and every EXISTING config's
behavior stay byte-identical. Touches no production file at RUNTIME.

Two modes
---------
--dry-run   (default; NO key, NO network)
    Proves the drop-in integration with zero LLM cost: the GENERATED CK25
    bank loads via BM25 through the real ``FewShotIndex``, retrieves
    same-shape examples for held-out questions, and injects a
    ``## Examples`` block into the prompt (the exact ``format_prompt_
    section`` call the NLQueryEngine makes) — REQ-4.

--sweep     (HUMAN-run: RUN_EVAL=1 + NL2SPARQL_API_KEY, gpt-4o-mini @ temp 0.1)
    Runs, back-to-back in ONE session (never against a stale
    ``baseline.json`` number — Pitfall 7):
      A) openai-gpt4o-mini-ck25-generated-fewshot  (CK25 + BM25 k=20 over
         the GENERATED bank)
      B) openai-gpt4o-mini-ck25                    (the EXISTING zero arm;
         FRESH same-session, never the committed historical baseline)
    over the same 49 held-out CK25 cases, then reports paired McNemar
    (b=gains, c=regressions) + a bootstrap CI on the pass-rate delta, BOTH
    raw AND overlap-EXCLUDED (REQ-6) — the excluded-case set comes from
    ``test_fewshot_bank_disjoint.py``'s ``overlapping_case_names`` (the
    SAME shape+entity overlap-audit source of truth Task 1 built, never
    re-derived here).

    Also runs the QALD-9-plus generated-fewshot arm ONCE as a
    non-regression check (expected muted/flat — QALD's generated bank is
    empty, RESEARCH OQ-4, a PASS not a failure).

    VERDICT (REQ-6 adopt bar): b>0, c==0 (zero regressions), delta>0
    surviving overlap-exclusion. Writes results to
    ``generated_sweep_result.json`` next to this file.
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
GENERATED_CK25_BANK = EVAL_DIR / "vendored" / "ck25" / "generated_fewshot_bank.yml"
RESULT = EVAL_DIR / "generated_sweep_result.json"

CK25_GENERATED_ARM = "openai-gpt4o-mini-ck25-generated-fewshot"
CK25_ZERO_ARM = "openai-gpt4o-mini-ck25"
QALD_GENERATED_ARM = "openai-gpt4o-mini-qald9plus-generated-fewshot"

# Held-out CK25 questions probed in --dry-run to show retrieval + prompt
# injection over the GENERATED bank (mirrors run_spike.py's DRY_RUN_PROBES —
# same held-out questions, same shapes: 2-hop / COUNT / top-N / top-N 2-hop).
DRY_RUN_PROBES = [
    "Who is the manager of the Data Services department?",  # ck25-7 (2-hop)
    "How many suppliers do we have in France?",             # ck25-13 (COUNT)
    "What is the cheapest Oscillator we have?",              # ck25-18 (top-N)
    "Which supplier delivers the most reliable Inductor?",   # ck25-45 (top-N 2-hop)
]


def dry_run() -> int:
    from arango_query_core.nl import cached_few_shot_index

    print("=" * 68)
    print("DRY RUN — no LLM, no network. Proving drop-in BM25 integration")
    print("over the GENERATED (query-first synthetic) CK25 bank.")
    print("=" * 68)

    idx = cached_few_shot_index(str(GENERATED_CK25_BANK), "bm25")
    n = len(idx.examples)
    print(f"\nGenerated bank loaded via BM25 FewShotIndex: {n} examples")
    # Track the committed bank's own example count rather than a magic number
    # (the bank moved 77 -> 73 after the Change-D degenerate-value exclusion,
    # 07.5-05; a hardcoded literal silently goes stale). This still catches a
    # partial/failed load — the real point of the assertion.
    import yaml

    expected = len(yaml.safe_load(GENERATED_CK25_BANK.read_text())["examples"])
    assert n == expected, f"index loaded {n} examples but {GENERATED_CK25_BANK.name} declares {expected}"
    assert type(idx.retriever).__name__ == "BM25Retriever", (
        f"expected BM25Retriever, got {type(idx.retriever).__name__} — install .[nl]"
    )

    print("\nRetrieval for held-out questions (top-3 same-shape examples):")
    for probe in DRY_RUN_PROBES:
        hits = idx.retrieve(probe, k=3)
        print(f"\n  held-out Q: {probe}")
        for q, _ in hits:
            print(f"      <- retrieved: {q}")

    print("\n" + "-" * 68)
    print("Prompt injection — the EXACT `## Examples` block the engine builds")
    print("(FewShotIndex.format_prompt_section) for ck25-7:")
    print("-" * 68)
    section = idx.format_prompt_section(DRY_RUN_PROBES[0], k=3, language="sparql")
    assert section.startswith("## Examples"), "no ## Examples section produced"
    print(section)
    print(
        "\nDRY RUN OK — generated bank loads, retrieves same-shape examples, "
        "injects prompt (REQ-4)."
    )
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
    from tests.nl2sparql.eval.test_fewshot_bank_disjoint import (
        CK25_CORPUS_PATH,
        GENERATED_CK25_BANK_PATH,
        _load_generated_bank,
        _positive_cases_for,
        overlapping_case_names,
    )

    print(f"Running GENERATED-BANK arm ({CK25_GENERATED_ARM}) ...")
    generated = run(CK25_GENERATED_ARM)
    cached_few_shot_index.cache_clear()
    print(f"Running FRESH-ZERO arm ({CK25_ZERO_ARM}) ...")
    zero = run(CK25_ZERO_ARM)

    zero_d = {c.name: c.passed for c in zero.cases}
    gen_d = {c.name: c.passed for c in generated.cases}

    b, c, p = paired_mcnemar(zero_d, gen_d)  # b=gains, c=regressions
    delta, lo, hi = bootstrap_paired_delta(zero_d, gen_d)

    gains = sorted(n for n in zero_d if not zero_d[n] and gen_d[n])
    regressions = sorted(n for n in zero_d if zero_d[n] and not gen_d[n])
    zpass = sum(zero_d.values())
    gpass = sum(gen_d.values())

    # Overlap-excluded delta (REQ-6) — same source of truth as the offline
    # audit (test_fewshot_bank_disjoint.py's shape+entity overlap helpers),
    # never re-derived here.
    bank_examples = _load_generated_bank(GENERATED_CK25_BANK_PATH)
    corpus_cases = _positive_cases_for(CK25_CORPUS_PATH)
    excluded_names = overlapping_case_names(bank_examples, corpus_cases)
    kept_names = set(zero_d) - excluded_names
    if kept_names:
        zero_ex = {n: zero_d[n] for n in kept_names}
        gen_ex = {n: gen_d[n] for n in kept_names}
        b_ex, c_ex, p_ex = paired_mcnemar(zero_ex, gen_ex)
        delta_ex, lo_ex, hi_ex = bootstrap_paired_delta(zero_ex, gen_ex)
    else:
        b_ex = c_ex = 0
        p_ex = 1.0
        delta_ex = lo_ex = hi_ex = 0.0

    print(f"Running QALD-9-plus generated-fewshot arm ({QALD_GENERATED_ARM}) — non-regression check ...")
    cached_few_shot_index.cache_clear()
    qald_generated = run(QALD_GENERATED_ARM)
    qald_pass = sum(1 for case in qald_generated.cases if case.passed)
    qald_total = len(qald_generated.cases)

    non_null = b > 0 and c == 0
    survives_exclusion = delta_ex > 0
    adopt = non_null and survives_exclusion
    verdict = (
        "ADOPT (b>0, c==0, delta>0 surviving overlap-exclusion)"
        if adopt
        else "KILL / documented-null (REQ-6 adopt bar not met)"
    )

    print("\n" + "=" * 68)
    print(f"  Zero arm       : {zpass}/{len(zero_d)} passed")
    print(f"  Generated arm  : {gpass}/{len(gen_d)} passed")
    print(f"  McNemar (raw)  : b(gains)={b}  c(regressions)={c}  p={p:.4f}")
    print(f"  Delta (raw)    : {delta:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  Excluded cases (shape+entity overlap axis, n={len(excluded_names)}): {sorted(excluded_names)}")
    print(f"  McNemar (excl) : b={b_ex}  c={c_ex}  p={p_ex:.4f}  (n={len(kept_names)})")
    print(f"  Delta (excl)   : {delta_ex:+.4f}  95% CI [{lo_ex:+.4f}, {hi_ex:+.4f}]")
    print(f"  Gains          (fail->pass): {gains}")
    print(f"  Regressions    (pass->fail): {regressions}")
    print(f"  QALD non-regression check  : {qald_pass}/{qald_total} passed")
    print(f"  VERDICT        : {verdict}")
    print("=" * 68)

    RESULT.write_text(json.dumps({
        "plan": "07.5-05",
        "arms": {"zero": CK25_ZERO_ARM, "generated": CK25_GENERATED_ARM, "qald": QALD_GENERATED_ARM},
        "model": "gpt-4o-mini", "temperature": 0.1,
        "n_cases": len(zero_d),
        "zero_pass": zpass, "generated_pass": gpass,
        "mcnemar_raw": {"b_gains": b, "c_regressions": c, "p_value": p},
        "bootstrap_delta_raw": {"delta": delta, "lo": lo, "hi": hi},
        "excluded_case_names": sorted(excluded_names),
        "mcnemar_overlap_excluded": {
            "b_gains": b_ex, "c_regressions": c_ex, "p_value": p_ex, "n": len(kept_names),
        },
        "bootstrap_delta_overlap_excluded": {"delta": delta_ex, "lo": lo_ex, "hi": hi_ex},
        "gains": gains, "regressions": regressions,
        "non_null": non_null, "survives_exclusion": survives_exclusion, "adopt": adopt,
        "qald_pass": qald_pass, "qald_total": qald_total,
        "zero_cases": zero_d, "generated_cases": gen_d,
    }, indent=2))
    print(f"\nWrote {RESULT}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="run the live paired sweep (needs key)")
    ap.add_argument("--dry-run", action="store_true", help="offline drop-in proof (default)")
    args = ap.parse_args()
    sys.exit(sweep() if args.sweep else dry_run())
