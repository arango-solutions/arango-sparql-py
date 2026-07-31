---
spike: 001
name: ck25-thin-fewshot-signal
type: standard
validates: "Given a thin, hand-built, entity-disjoint few-shot bank (3 shapes) injected via the existing BM25 FewShotIndex, when the 49 held-out CK25 questions are run through the live NL→SPARQL pipeline, then at least one currently-failing case flips fail→pass with net gains > 0 (b > c)."
verdict: PENDING
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
6. **Verdict pending the one credentialed sweep** (human-held key) — the only
   step the agent cannot run.

## Results

**PENDING** — awaiting the credentialed `--sweep`. Everything the agent can
verify offline is green:

- 9/9 examples parse, transpile to non-empty AQL, execute non-empty vs CK25
  data, and are algebra-disjoint from all 49 held-out golds.
- The 3 top-N examples have strictly-unique extrema (deterministic under LIMIT 1).
- The bank loads through the production BM25 `FewShotIndex`, retrieves same-shape
  examples for the held-out questions, and injects a real `## Examples` prompt
  section.

The fail→pass signal itself is what the human sweep decides.

╔══════════════════════════════════════════════════════════════╗
║  CHECKPOINT: Verification Required (human, credentialed)      ║
╚══════════════════════════════════════════════════════════════╝

**Spike 001 — CK25 thin few-shot signal**
**Run:**
```
RUN_EVAL=1 NL2SPARQL_API_KEY=… \
  uv run python .planning/spikes/001-ck25-thin-fewshot-signal/run_spike.py --sweep
```
**What to expect:** two arms over the same 49 held-out CK25 cases, then
`b`(gains)/`c`(regressions)/McNemar `p`/bootstrap delta and the flipped-case
lists; `spike_result.json` written next to this README.

──────────────────────────────────────────────────────────────
→ Paste back the printed block (or `spike_result.json`). Non-null (b ≥ 1, b > c)
  → the D-01 gate opens and the full generator build is justified. Null → kill or
  rethink the lever before building.
──────────────────────────────────────────────────────────────
