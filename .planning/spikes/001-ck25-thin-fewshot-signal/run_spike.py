"""Spike 001 runner — D-01 Stage 0 gate: does a thin hand-built few-shot bank
move ANY held-out CK25 case?

FULLY ISOLATED: monkeypatches the eval runner in-process (inject one spike arm
+ point BANK_PATH at the thin spike bank). Touches NO production file
(configs.yml / runner.py / fewshot_bank.yml are all unmodified).

Two modes
---------
--dry-run   (default; NO key, NO network)
    Proves the drop-in integration with zero LLM cost: the thin bank loads via
    BM25 through the real FewShotIndex, retrieves same-shape examples for the
    held-out questions, and injects a `## Examples` block into the prompt
    (the exact `format_prompt_section` call the NLQueryEngine makes).

--sweep     (HUMAN-run: RUN_EVAL=1 + NL2SPARQL_API_KEY, gpt-4o-mini @ temp 0.1)
    Runs, back-to-back in ONE session:
      A) ck25-thin-fewshot-spike  (CK25 corpus + few_shot bm25 k=3 -> thin bank)
      B) openai-gpt4o-mini-ck25   (the EXISTING zero arm; fresh same-session)
    over the same 49 held-out cases, then reports paired McNemar (b=gains,
    c=regressions), a bootstrap CI on the pass-rate delta, and the exact list
    of flipped cases. Writes results to spike_result.json next to this file.

    VERDICT (D-01): non-null == at least one held-out case flips fail->pass with
    net gains > 0 (b > c). A null (b == 0, or c >= b) kills the full generator.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.chdir(REPO)

BANK = Path(__file__).resolve().parent / "ck25_thin_fewshot_bank.yml"
RESULT = Path(__file__).resolve().parent / "spike_result.json"

# The spike arm: CK25 held-out corpus + BM25 few-shot at k=3. Identical to the
# existing zero arm (openai-gpt4o-mini-ck25) EXCEPT the additive few_shot block,
# so the comparison isolates the examples' effect and nothing else.
SPIKE_ARM = "ck25-thin-fewshot-spike"
ZERO_ARM = "openai-gpt4o-mini-ck25"
SPIKE_CONFIG = {
    "provider": {"type": "openai", "model": "gpt-4o-mini"},
    "judge": "execution",
    "max_repairs": 2,
    "corpus": "vendored/ck25/corpus.yml",
    "few_shot": {"mode": "bm25", "k": 3},
}

# Held-out questions probed in --dry-run to show retrieval + prompt injection.
DRY_RUN_PROBES = [
    "Who is the manager of the Data Services department?",  # ck25-7 (2-hop)
    "How many suppliers do we have in France?",             # ck25-13 (COUNT)
    "What is the cheapest Oscillator we have?",             # ck25-18 (top-N)
    "Which supplier delivers the most reliable Inductor?",  # ck25-45 (top-N 2-hop)
]


def _patch_runner():
    """Inject the spike arm and repoint the few-shot bank — isolation only."""
    import tests.nl2sparql.eval.runner as R

    orig_load = R._load_configs

    def patched_load():
        d = orig_load()
        d["configs"][SPIKE_ARM] = dict(SPIKE_CONFIG)
        return d

    R._load_configs = patched_load
    R.BANK_PATH = BANK
    R.cached_few_shot_index.cache_clear()
    return R


def dry_run() -> int:
    from arango_query_core.nl import cached_few_shot_index

    print("=" * 68)
    print("DRY RUN — no LLM, no network. Proving drop-in BM25 integration.")
    print("=" * 68)

    idx = cached_few_shot_index(str(BANK), "bm25")
    n = len(idx.examples)
    print(f"\nBank loaded via BM25 FewShotIndex: {n} examples")
    assert n == 9, f"expected 9 examples, got {n}"
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
    print("\nDRY RUN OK — bank loads, retrieves same-shape examples, injects prompt.")
    return 0


def sweep() -> int:
    if os.getenv("RUN_EVAL", "").strip().lower() in ("", "0", "false", "no"):
        print("ERROR: set RUN_EVAL=1 to run the live sweep.", file=sys.stderr)
        return 2
    if not os.getenv("NL2SPARQL_API_KEY"):
        print("ERROR: NL2SPARQL_API_KEY must be set (human-held key).", file=sys.stderr)
        return 2

    R = _patch_runner()

    print("Running THIN-BANK arm (ck25-thin-fewshot-spike) ...")
    thin = R.run(SPIKE_ARM)
    R.cached_few_shot_index.cache_clear()
    print("Running FRESH-ZERO arm (openai-gpt4o-mini-ck25) ...")
    zero = R.run(ZERO_ARM)

    zero_d = {c.name: c.passed for c in zero.cases}
    thin_d = {c.name: c.passed for c in thin.cases}

    b, c, p = R.paired_mcnemar(zero_d, thin_d)  # b=gains, c=regressions
    delta, lo, hi = R.bootstrap_paired_delta(zero_d, thin_d)

    gains = sorted(n for n in zero_d if not zero_d[n] and thin_d[n])
    regressions = sorted(n for n in zero_d if zero_d[n] and not thin_d[n])
    zpass = sum(zero_d.values())
    tpass = sum(thin_d.values())

    non_null = b > 0 and b > c
    verdict = "NON-NULL (signal — proceed to full build)" if non_null else \
              "NULL (kill / rethink — thin bank moved nothing net-positive)"

    print("\n" + "=" * 68)
    print(f"  Zero arm : {zpass}/{len(zero_d)} passed")
    print(f"  Thin arm : {tpass}/{len(thin_d)} passed")
    print(f"  McNemar  : b(gains)={b}  c(regressions)={c}  p={p:.4f}")
    print(f"  Delta    : {delta:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  Gains        (fail->pass): {gains}")
    print(f"  Regressions  (pass->fail): {regressions}")
    print(f"  VERDICT  : {verdict}")
    print("=" * 68)

    RESULT.write_text(json.dumps({
        "spike": "001-ck25-thin-fewshot-signal",
        "arms": {"zero": ZERO_ARM, "thin": SPIKE_ARM},
        "model": "gpt-4o-mini", "temperature": 0.1,
        "n_cases": len(zero_d),
        "zero_pass": zpass, "thin_pass": tpass,
        "mcnemar": {"b_gains": b, "c_regressions": c, "p_value": p},
        "bootstrap_delta": {"delta": delta, "lo": lo, "hi": hi},
        "gains": gains, "regressions": regressions,
        "non_null": non_null,
        "zero_cases": zero_d, "thin_cases": thin_d,
    }, indent=2))
    print(f"\nWrote {RESULT}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="run the live paired sweep (needs key)")
    args = ap.parse_args()
    sys.exit(sweep() if args.sweep else dry_run())
