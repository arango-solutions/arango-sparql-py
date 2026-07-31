# Spike Manifest

## Idea

De-risk **Phase 07.5** (NL→SPARQL query-first synthetic few-shot bank) at its
load-bearing gate. Phase 07.5 proposes a build-time generator that emits
per-ontology `(question, gold-SPARQL)` few-shot banks so NL→SPARQL specializes
to any new ontology without hand-curation. Decision **D-01** requires a **Stage 0
spike** before committing the multi-wave build: hand-build a thin slice of
examples for 2–3 shapes on CK25 and check whether injecting them (through the
existing BM25 `FewShotIndex`) moves *any* held-out CK25 case. Non-null → build;
null → kill the lever.

## Requirements

Design decisions that constrain the spike (and the eventual build), from the
07.5 SPEC/CONTEXT and confirmed here:

- Examples must be **leakage-safe**: same query *shape* as failing held-out cases
  (so BM25 retrieves them) but **entity-disjoint** on both the entity and
  query-shape axes (D-05) — no held-out answers memorized.
- Bank loads through the **existing BM25 `FewShotIndex` / `fewshot_bank.yml`
  format** — no new retrieval code.
- Grading is **mechanistic + directional** (answer-set execution judge); the
  benchmark is underpowered, so there is no significance gate — the D-01 verdict
  is "does *any* case flip fail→pass, net of regressions."
- Non-regression: touch **no** production eval file for the spike; the credentialed
  sweep is **human-run** (`NL2SPARQL_API_KEY` never held by the agent).

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | ck25-thin-fewshot-signal | standard | Thin hand-built 3-shape entity-disjoint bank, injected via BM25, moves ≥1 held-out CK25 case fail→pass (b>c) | PENDING (offline gates green; awaiting human `--sweep`) | nl2sparql, few-shot, ck25, phase-07.5, stage-0-gate |
