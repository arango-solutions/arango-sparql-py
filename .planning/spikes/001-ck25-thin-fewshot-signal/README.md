---
spike: 001
name: ck25-thin-fewshot-signal
type: standard
validates: "Given a thin, hand-built, entity-disjoint few-shot bank (3 shapes) injected via the existing BM25 FewShotIndex, when the 49 held-out CK25 questions are run through the live NL→SPARQL pipeline, then at least one currently-failing case flips fail→pass with net gains > 0 (b > c)."
verdict: VALIDATED
related: []
tags: [nl2sparql, few-shot, ck25, phase-07.5, stage-0-gate, bm25, de-risk]
---

# Spike 001: CK25 thin few-shot signal (Phase 07.5, D-01 Stage 0 gate)

## What This Validates

Phase 07.5 proposes a build-time **generator** that emits per-ontology
`(question, gold-SPARQL)` few-shot banks. Decision **D-01** put a cheap de-risk
gate in front of that multi-wave build:

> **Given** a thin slice — 2–3 shapes, CK25 only, HAND-BUILT generated examples —
> **when** they are injected through the existing BM25 `FewShotIndex`,
> **then** does adding them move *any* held-out CK25 case?

If hand-crafted examples move nothing, the full generator is pointless — **kill
before building**. This spike proves (or refutes) that the *lever* exists before
building the *machine that pulls it*.

## Research

- **Where the signal can live** — Of the 49 held-out CK25 cases, only 6 pass at
  the zero baseline (`baseline.json` `openai-gpt4o-mini-ck25`). The failures
  cluster by gold-query shape; the three richest buckets are **2-hop join
  (12/12 failing)**, **top-N ORDER BY+LIMIT (10–11/12 failing)**, and **scalar
  COUNT (6/8 failing)** — 28 of 43 failures. Critically, these three are *not*
  rescued by the already-shipped entity-grounding lever (07.3), so any movement
  here is attributable to the examples, not to grounding. These are the spike's
  three target shapes.
- **The examples teach composition, not IRIs.** Most CK25 failures hardcode
  instance IRIs (`<…dept-41622>`) — that is the *entity-grounding* problem, a
  different (shipped) lever. So the bank teaches **name-anchored composition**
  (`?d pv:name "Engineering"` instead of a hardcoded IRI): the IRI-free,
  generalizable pattern the future generator would emit. Under the **answer-set
  execution judge**, a name-join query returns the same rows as the
  IRI-hardcoded gold, so it is a legitimate signal path *and* it is structurally
  disjoint from every held-out gold.
- **Leakage-safety (D-05).** Same *shape* as the failing cases (so BM25 retrieves
  them) but **entity-disjoint**: departments Engineering/Procurement (never Data
  Services/Marketing); categories Crystal/Capacitor/Resistor/Rheostat/
  Multiplexer/Gauge (never Compensator/Oscillator/Inductor/Encoder/Coil/…);
  country India (never France/Germany/US/Poland/Russia). A lift is therefore
  real compositional learning, not memorized test answers.

## Files

| File | Purpose |
|------|---------|
| `ck25_thin_fewshot_bank.yml` | The 9 hand-built examples (3 per shape). |
| `verify_bank.py` | No-LLM gate: every example parses, transpiles to non-empty AQL, executes non-empty vs `prod-inst.ttl`, top-N extrema strictly unique, and is algebra-disjoint from all 49 held-out golds. |
| `run_spike.py` | Isolated runner. `--dry-run` (no key) proves BM25 load + prompt injection; `--sweep` (human key) runs the paired thin-vs-zero comparison. |
| `spike_result.json` | Written by `--sweep`: per-case verdicts, McNemar, bootstrap CI, flipped-case lists. |

**Isolation:** `run_spike.py` monkeypatches the eval runner in-process (injects
one spike arm, repoints `BANK_PATH`). It modifies **no** production file —
`configs.yml`, `runner.py`, and `fewshot_bank.yml` are untouched.

## How to Run

**Agent-verifiable (done, no key):**
```bash
uv run python .planning/spikes/001-ck25-thin-fewshot-signal/verify_bank.py
uv run python .planning/spikes/001-ck25-thin-fewshot-signal/run_spike.py   # --dry-run
```

**The one human step (credentialed, gpt-4o-mini @ temp 0.1):**
```bash
RUN_EVAL=1 NL2SPARQL_API_KEY=… \
  uv run python .planning/spikes/001-ck25-thin-fewshot-signal/run_spike.py --sweep
```
Runs the thin-bank arm and the fresh-zero arm back-to-back over the same 49
held-out cases, prints the paired result, and writes `spike_result.json`. Your
key is never held by the agent and never written to any file.

## What to Expect

- **verify_bank.py** → `ALL GREEN` (9/9 examples valid; the 3 top-N examples
  report `rank1 > rank2`).
- **--dry-run** → bank loads as 9 BM25 examples; each held-out probe retrieves
  *same-shape* examples (2-hop→2-hop, COUNT→COUNT, top-N→top-N); a real
  `## Examples` block is printed.
- **--sweep** → `b` (fail→pass gains), `c` (pass→fail regressions), McNemar `p`,
  bootstrap delta CI, and the flipped-case lists.
  **Non-null (proceed):** `b ≥ 1` and `b > c`. **Null (kill / rethink):** `b == 0`
  or `c ≥ b`.

## Observability

`run_spike.py --sweep` writes `spike_result.json` with the full per-case verdict
maps for both arms (`zero_cases`, `thin_cases`), so the flip set is auditable and
the run is foldable into the phase record without re-running.

## Investigation Trail

1. **Reframed the ask.** `/gsd-spike` with no argument defaulted to frontier
   mode, but STATE.md + the 07.5 CONTEXT showed this is the D-01 Stage 0 *gate* —
   an idea-mode spike with an already-defined question — sitting between the
   finished discussion and the multi-wave plan.
2. **Grounded the shape choice in real failure data** rather than guessing:
   mapped the 49 held-out golds to shape buckets and cross-tabbed against the
   recorded zero-arm verdicts. 2-hop / top-N / scalar-COUNT chosen (most
   failures, unrescued by grounding).
3. **Chose name-anchored composition** over IRI-hardcoded golds once it was clear
   most failures are entity-grounding (a separate lever) — so the examples target
   the *compositional* failure mode this lever can actually address, and stay
   disjoint from the golds.
4. **Authored + verified 9 examples.** First pass: 8/9 green; **example 8
   (Transformer, heaviest) failed on a weight tie** (20.0 == 20.0). Probing
   revealed `weight_g` is saturated at 20.0 across *every* category — a bad
   top-N attribute. Swapped to "widest Rheostat" (`width_mm`, 80.0 > 76.0,
   strictly unique). Re-verified `ALL GREEN`.
5. **Proved drop-in integration with zero LLM cost** via `--dry-run`: BM25
   retrieval is shape-aware and the real `## Examples` block injects.
6. **Credentialed sweep run** (human key, gpt-4o-mini @ temp 0.1, 2026-07-31) —
   decisive NON-NULL (see Results). The one step the agent could not run.

## Results

**VALIDATED** — the lever exists. Credentialed paired sweep (gpt-4o-mini @ temp
0.1, same 49 held-out cases, thin-bank arm vs fresh same-session zero arm;
`spike_result.json`):

| Metric | Value |
|--------|-------|
| Zero arm | **5 / 49** passed |
| Thin-bank arm | **15 / 49** passed |
| McNemar | **b (gains) = 11, c (regressions) = 1, p = 0.0063** |
| Bootstrap delta | **+0.204, 95% CI [+0.082, +0.327]** (excludes 0) |

**Gains (11, fail→pass):** ck25-2, 7, 10, 11, 12, 13, 15, 17, 18, 19, 45.
**Regression (1, pass→fail):** ck25-30.

- **The gains land exactly on the targeted shapes** — 2-hop (7, 10, 11, 12, 17),
  scalar COUNT (13), top-N (15, 18, 19, 45) — plus a lookup bonus (ck25-2). This
  is the failure analysis confirmed: examples helped precisely the buckets they
  targeted, and the name-anchored composition pattern generalized (the model
  produced shape-correct queries that execute to the gold answer set, sidestepping
  the IRI-grounding problem as designed).
- **The single regression is honest and expected.** ck25-30 is a
  `GROUP BY … HAVING(COUNT > 5)` grouped-aggregation — a shape **not** in the thin
  bank; the scalar-COUNT examples plausibly nudged it toward a scalar count. It is
  a distraction loss, and it is dwarfed 11:1 by the gains. It also foreshadows a
  real design point for the full generator: grouped aggregation (GROUP BY/HAVING)
  is a distinct shape that needs its own coverage, not just scalar COUNT.

**Offline gates (all green, pre-sweep):** 9/9 examples parse, transpile to
non-empty AQL, execute non-empty vs CK25 data, and are algebra-disjoint from the
49 held-out golds; the 3 top-N examples have strictly-unique extrema; the bank
loads through the production BM25 `FewShotIndex` and injects a real `## Examples`
section.

### D-01 gate: OPEN

The Stage 0 signal is non-null (b=11 ≫ c=1, p=0.0063). Per D-01 the full
generator build (Stage 1 eval prototype → Stage 2 engine promotion) is justified.
Carry-forward requirements the spike surfaced for Phase 07.5:

1. **Name-anchored composition is the winning example form** — the generator
   should emit label/name-resolved patterns, not hardcoded instance IRIs (it
   sidesteps the orthogonal entity-grounding bottleneck and is what generalized
   here).
2. **Grouped aggregation (GROUP BY/HAVING) is its own shape** — the ck25-30
   regression shows scalar-COUNT coverage does not cover it and can even distract
   it; the generator's ≥7-shape target must treat grouped aggregation distinctly
   and the per-shape-yield report (D-02) must track it.
3. **Watch net regressions at scale** — one distraction loss appeared even in a
   9-example bank; the full measurement's "zero regressions" adopt bar (SPEC
   REQ-6) is a real constraint, not a formality.
