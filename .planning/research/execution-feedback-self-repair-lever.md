# Lever design (PARKED): execution-feedback self-repair loop

> **Status:** PARKED — v2 lever, gated on corpus growth (Phase 07.1). Do NOT build yet.
> **Captured:** 2026-07-29, from a brainstorming session after the predicate-rendering fix.
> **Related:** [[expasy-schema-context-levers]] (lever inventory; this is the "run-it-and-retry"
> idea, distinct from the dead EGS and from schema-context injection).

## Idea (one line)

Add an "did it actually return anything?" check to the NL engine's **existing**
generate→validate→repair→retry loop, so a query that runs but comes back empty (or errors)
gets one re-prompt with that feedback and a second attempt.

## Design (how it would be built)

- **Extend, don't rebuild.** `arango_query_core/nl/engine.py` already runs a
  generate → validate (`ValidationResult`) → `adapter.repair_hint` → retry loop (budget
  `max_repairs`). Add a new **execution validator** into that loop — same machinery, new trigger.
- **Backend-agnostic executor (the one new interface).** The engine takes an optional injected
  `executor: query -> (ran_ok, row_count)`. It never knows *how* the query runs. Eval injects a
  **pyoxigraph** executor over the corpus data (already the judge backend); production later injects
  transpile→AQL→ArangoDB; Cypher injects its own. Gated **off by default** (no executor = no-op),
  like `grounding_k=0`. Engine-side ⇒ Cypher inherits.
- **Feedback (repair hint):** minimal — *"That query executed but returned no rows; it may use a
  property that doesn't fit or over-constrain the pattern. Revise it."* Per-triple diagnostics are a
  deferred v3.
- **Budget:** reuse `max_repairs`, default 1 for the first experiment.
- **Deliverable = measurement:** a config knob turns the execution validator on for the additive
  arm; run on vs off, 3×, report net pass delta AND a regression count.

## Why it's parked (data-backed gaps, CK25, 2026-07-29)

Measured against the real CK25 corpus + gold queries:

1. **The "0 rows" trigger only applies to ~⅔ of questions.** Of 49: 3 ASK, 13 aggregation/COUNT,
   33 plain SELECT.
   - **ASK** returns a boolean, never rows; `ASK → false` is a *valid* answer — retrying it is
     harmful. The validator must detect and skip ASK.
   - **COUNT/aggregation** always returns exactly **one row** (the number), even when wrong — the
     0-rows trigger *never fires* for the 13 aggregation questions. Would need value-level logic
     (`count == 0`), which still misses wrong-but-nonzero counts.
   - ⇒ Real reach is the ~33 SELECTs, and the validator must be scoped to row-returning SELECTs.
2. **Legit-empty risk is ~0 on CK25 — which is a measurement trap, not a reassurance.** 0 gold
   answers are empty (0 ASK-false, 0 empty SELECT among the 44 evaluable golds; CK25 is curated so
   every question has an answer). So CK25 *cannot* exercise the "retry corrupts a correct-empty
   answer" failure mode. Production/other corpora WILL have legit-empty questions ("suppliers in
   Antarctica"), needing a guard the eval can never test. Eval-green ≠ production-safe.
3. **Executor coverage confounds the error trigger.** 5 gold queries don't even run in pyoxigraph
   (parse/runtime errors). "error → retry" can't distinguish a genuinely-broken candidate from a
   valid query using a feature the engine doesn't support; retrying the latter is wrong. ArangoDB
   (production) has a different support profile, so the confound changes between eval and prod.
4. **The validator is a weak proxy for the judge.** It checks "any rows came back," not "the *right*
   rows." Blind to all 15 wrong-but-non-empty failures; a query that passes the validator is often
   still wrong. The loop only ever touches the empty subset.
5. **Measurement power gets worse.** Each retry is a *second* stochastic generation. At n=49 /
   temp 0.1 — where the rendering fix's +2–3 was already within noise — separating the loop's true
   effect from added variance is harder, not easier.
6. **Production cost the eval hides.** "Run it mid-generation" in production = transpile→AQL→ArangoDB
   round-trip on every request, DB reachable at generation time. Eval (in-process pyoxigraph) is free.

## Reach ceiling (measured)

Of 39 failing cases in the recorded additive run: 24/39 (62%) are retry-*catchable* (return empty or
error — 17 run-but-0-rows, 6 empty-generation, 1 error); 15/39 (38%) return wrong-but-non-empty and
are invisible to the loop. "Catchable" ≠ "fixable" — the retry still has to produce a correct query.

## Revisit criteria (when to build)

- **After Phase 07.1 corpus growth** lifts the corpus enough that the MDE is below the effect this
  could plausibly produce (at 49 cases with ⅓ trigger-blind, it can't be shown to move the number).
- Scope the validator to row-returning SELECTs from day one; handle ASK/aggregation explicitly.
- Split the trigger: treat "empty result" and "executor error" as distinct signals; be conservative
  retrying on error (engine-coverage gap vs wrong query).
- Add — and separately test — a production-only legit-empty guard, knowing CK25 won't exercise it.
- Define a concrete ship bar (net delta over N runs with an explicit regression cap), not "gains beat
  regressions" hand-waving.

## Next actual work

Corpus growth (Phase 07.1), which is the shared prerequisite for this lever, the few-shot-exemplar
lever, and proving any schema lever. This loop waits behind it.
