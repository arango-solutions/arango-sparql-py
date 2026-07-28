---
phase: 04-interoperability-performance-verification
plan: 06
subsystem: testing
tags: [perf, pytest, fastapi, testclient, p95, statistics, ci-gate]

# Dependency graph
requires:
  - phase: 04-01
    provides: "tests/perf/ package scaffolding (fake ArangoDB double reuse, p95/load_baseline/append_report helpers)"
provides:
  - "Three CI-gated, fully in-process D-08 perf rows: /translate cold, /translate warm, /execute overhead"
  - "tests/perf/baseline.json checked-in baseline with env-matched gating (captured_env)"
  - "Env-matched p95 gate pattern (hard-enforce on env match, advisory warn+pass on mismatch) reusable by report-only rows (Plan 07)"
affects: ["04-07 (report-only perf rows)", "CI wiring for the perf-gated fast path"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "gc.collect()+gc.disable() around a timed measurement loop to keep a mid-loop cyclic-collector pass out of the p95 bucket"
    - "logging.disable(logging.CRITICAL) around a timed measurement loop so per-request INFO logging I/O doesn't skew p95"
    - "env-matched baseline gating: captured_env tag on baseline.json + 'ci' if os.environ.get('CI') else 'local' at run time; hard assert only on match, warnings.warn+pass otherwise"

key-files:
  created:
    - tests/perf/test_translate_latency.py
    - tests/perf/test_execute_overhead.py
    - tests/perf/baseline.json
  modified: []

key-decisions:
  - "translate_cold/translate_warm distinguished by payload construction, not a caching layer: cold builds a distinct, never-before-seen Turtle+SPARQL pair per iteration (indexed class/property local names) forcing a genuinely fresh parse+resolve each call; warm reuses the exact same payload every iteration. The route itself has no resolver-level cache today (verified: _graph_from_request/_resolver_from_request parse a fresh rdflib.Graph on every call) so this models the PRD's cold-vs-warm distinction at the request-shape level rather than an implementation-level cache that doesn't exist yet."
  - "test_execute_overhead.py explicitly clears OPENAI_API_KEY/ANTHROPIC_API_KEY/OPENROUTER_API_KEY/LLM_PROVIDER/SCHEMA_ANALYZER_PROVIDER for the duration of the test (Rule 2): /execute's analyzer-enrichment path (_analyzer_bundle_for_session -> _get_or_acquire, strategy='auto') resolves an LLM provider from the environment when arangodb-schema-analyzer is installed, and this repo's own .env sets OPENAI_API_KEY. Today it fails fast against _FakeDb (no .collections()) and degrades silently, but a CI-gated, Docker/network-free perf row must not depend on that failure-ordering coincidence never changing."
  - "Both perf test files suppress per-request INFO logging (logging.disable) and defer GC (gc.collect()+gc.disable()) for the duration of the measurement loop (Rule 1): empirically, logging I/O and mid-loop GC passes were landing inside the p95 bucket and destabilizing the gate with noise unrelated to the measured translate/dispatch work -- this is the T-04-12 'stable central value' mitigation applied at the measurement-hygiene level, not just the baseline-selection level."
  - "ASK query pinned to a typed pattern ('ASK { ?s a :Thing }', matching the proven tests/translate/ask.yml golden) rather than an untyped '?s ?p ?o' triple, to avoid depending on unverified resolver behavior for a fully-variable BGP."
  - "baseline.json committed with captured_env='local' as the plan-sanctioned interim bootstrap (captured on this dev sandbox, not a CI runner) -- see 'Known Limitations' below for why the authoritative CI capture matters more than usual here."

patterns-established:
  - "Env-matched perf gate: any future report-only or CI-gated perf row (Plan 07) should reuse the captured_env tag + hard-enforce-on-match/advisory-on-mismatch pattern rather than inventing a new gating scheme."

requirements-completed: [REQ-performance-slos]

# Metrics
duration: ~45min
completed: 2026-07-28
---

# Phase 04 Plan 06: CI-Gated Perf Tier (translate cold/warm + execute overhead) Summary

Delivered the three D-08 CI-blocking perf rows fully in-process (zero Docker, zero real DB, zero network) — `/translate` cold and warm p95 gates plus a `/execute` overhead p95 gate stubbed via the proven `_FakeArangoClient` double — each measured with `statistics.quantiles` (N=120, 20-sample warmup discard) and gated at `p95 <= baseline * 1.25` only when the run's environment matches the checked-in baseline's `captured_env`.

## Performance

- **Duration:** ~45 min
- **Tasks:** 2 completed
- **Files modified:** 3 (all created)

## Accomplishments
- `tests/perf/test_translate_latency.py`: two rows (`translate_cold_p95_ms`, `translate_warm_p95_ms`) exercising `/translate` with no session (translate never touches a DB), cold using a distinct never-before-seen ontology+query per iteration, warm reusing one fixed payload across all 120 iterations.
- `tests/perf/test_execute_overhead.py`: `execute_overhead_p95_ms` row exercising `/connect` -> `/execute` with `svc.ArangoClient` monkeypatched to `_FakeArangoClient` (via the re-exported `fake_client_factory` fixture) and AQL pinned to a trivial `ASK { ?s a :Thing }` query so the fake cursor returns instantly — the row measures translate+dispatch overhead, explicitly excluding AQL execution time, per PRD §9.4.
- All three rows implement the environment-matched gate: `captured_env` read from `baseline.json`, current env computed as `"ci" if os.environ.get("CI") else "local"`; hard `assert p95 <= baseline * 1.25` only fires on an env match, otherwise `warnings.warn(...)` with both numbers and the test passes (advisory). A missing baseline row (first-capture-run) is handled with `pytest.skip`.
- `tests/perf/baseline.json` checked in with `generated_at`, `captured_env: "local"`, and exactly the three CI-gated rows (`translate_cold_p95_ms: 2.3`, `translate_warm_p95_ms: 2.3`, `execute_overhead_p95_ms: 1.9`), captured as a stable median across many repeated capture runs on this sandbox (not a single jitter spike).
- Verified green across 5 consecutive `pytest tests/perf/test_translate_latency.py tests/perf/test_execute_overhead.py -m perf -q` runs against the committed baseline, and the full non-regression suite (`pytest -m "not integration and not w3c and not eval and not perf" -q`) stays green at 1428 passed.
- Neither file imports `pytest-benchmark`, `numpy`, or `scipy` — percentiles computed exclusively via the stdlib `p95()` helper re-exported from `tests/perf/conftest.py` (Plan 01).

## Task Commits

Each task was committed atomically:

1. **Task 1: CI-gated translate + execute p95 perf tests** - `63c93f6` (feat)
2. **Task 2: Capture and commit the CI-gated baseline.json** - `5df0e45` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `tests/perf/test_translate_latency.py` - `/translate` cold + warm p95 rows, env-matched gate, `_quiet_logging()` (logging suppress + GC defer) measurement-hygiene context manager
- `tests/perf/test_execute_overhead.py` - `/execute` overhead p95 row stubbed via `fake_client_factory`, same env-matched gate + measurement hygiene, plus an LLM-provider env-var scrub for determinism
- `tests/perf/baseline.json` - checked-in baseline: `generated_at`, `captured_env: "local"`, and the three CI-gated `rows`

## Decisions Made
See `key-decisions` in frontmatter. In summary: (1) cold/warm distinguished at the request-payload level since no resolver cache exists yet in the route layer; (2) `/execute`'s analyzer-enrichment path explicitly denied any LLM provider env var for the duration of the test, closing a latent network-dependency risk that isn't gated by any existing test; (3) logging suppression + GC deferral added to both measurement loops after empirically observing that per-request INFO log I/O and mid-loop GC passes were the dominant source of p95 instability in this sandbox, not the actual translate/dispatch work; (4) the ASK query is pinned to the exact `ask_type_only` golden shape rather than an untyped triple pattern, to avoid depending on unverified resolver behavior for this fast-path perf test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Forced `/execute`'s analyzer-enrichment path to the deterministic-baseline branch for the duration of the perf test**
- **Found during:** Task 1 (writing `test_execute_overhead.py`)
- **Issue:** `/execute`'s `_analyzer_bundle_for_session` -> `_get_or_acquire(strategy="auto")` resolves an LLM provider from `OPENAI_API_KEY`/`LLM_PROVIDER`/etc. when `arangodb-schema-analyzer` is importable. This repo's `.env` sets `OPENAI_API_KEY`, so an initial capture run logged `schema-analyzer using LLM provider=openai` on every `/execute` call. It currently fails fast against `_FakeDb` (no `.collections()`) and degrades silently to `None`, so no real network call is made today — but a CI-gated, "zero Docker, zero network" perf row must not rely on that failure-ordering coincidence surviving future refactors.
- **Fix:** `monkeypatch.delenv` for `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`/`LLM_PROVIDER`/`SCHEMA_ANALYZER_PROVIDER` at the top of `test_execute_overhead_p95`, forcing `_resolve_analyzer_provider()` to return `None` deterministically regardless of the host's ambient `.env`.
- **Files modified:** `tests/perf/test_execute_overhead.py`
- **Verification:** Re-ran the full perf test suite; still green, and the `schema-analyzer using LLM provider=openai` log line no longer appears during the loop.
- **Committed in:** `5df0e45` (Task 2 commit)

**2. [Rule 1 - Bug] Suppressed per-request logging and deferred GC during the measurement loop to stop a flaky p95 gate**
- **Found during:** Task 2 (baseline capture)
- **Issue:** Initial capture runs showed p95 values swinging up to ~3x their typical value across repeated identical invocations (e.g. `translate_warm_p95_ms` measured anywhere from ~2.0ms to ~8.4ms run-to-run) — an unstable measurement is a correctness bug for a hard CI gate, not an acceptable "just pick a bigger baseline" situation.
- **Fix:** Added a `_quiet_logging()` context manager (duplicated identically in both files, matching the existing `_gate()` duplication convention) that suppresses `logging` at `CRITICAL` and runs `gc.collect()` + `gc.disable()` for the duration of the timed loop, restoring both in a `finally` block. This measurably tightened (but did not fully eliminate) the outlier spikes.
- **Files modified:** `tests/perf/test_translate_latency.py`, `tests/perf/test_execute_overhead.py`
- **Verification:** 5 consecutive full-suite runs green against the committed baseline post-fix.
- **Committed in:** `5df0e45` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing-critical/Rule 2, 1 bug/Rule 1)
**Impact on plan:** Both fixes are measurement-hygiene and determinism hardening for a perf test that must be genuinely dependency-free and stable — no scope creep, no behavior change to the routes under test.

## Issues Encountered

**Higher-than-expected jitter in this execution sandbox.** Even after the logging/GC hygiene fix, repeated captures in this interactive dev sandbox still occasionally produced a p95 spike roughly 2-3x the typical value (observed in ~1 of every 5-8 runs across dozens of capture repetitions). This appears to be environmental (shared/virtualized CPU scheduling in this specific sandbox), not a bug in the measured code path or the test harness — the same loop, timed the same way, is tight and consistent in the large majority of runs. The committed `baseline.json` values were chosen as the median of many repeated runs (not a single favorable reading), and 5 consecutive full verification runs passed cleanly against them, but a rare local re-run in this same sandbox could still trip the hard gate. This is exactly the scenario the plan's `captured_env`/env-matched gating was designed to bound in the long run: once the authoritative baseline is captured from a real (dedicated) CI runner with `captured_env: "ci"`, a local re-run on a noisy dev machine like this one will automatically fall back to the advisory `warnings.warn` path instead of hard-failing, because `captured_env` will no longer equal the local run's `"local"` environment tag.

## Known Limitations / Follow-up Required

**The committed `baseline.json` has `captured_env: "local"`, captured on this interactive dev sandbox — not the authoritative CI capture the plan calls for.** Per the plan's own explicit allowance ("a locally-captured `captured_env: "local"` baseline is acceptable as an interim bootstrap but only gates local runs"), this is the expected interim state, but it means:
- On a real CI run (`CI` env var set), the current baseline's `captured_env="local"` will not match the run's `"ci"` environment tag, so **the gate degrades to advisory (warn + pass) on every CI run until a CI-captured baseline replaces this one.**
- **Follow-up required:** capture a fresh baseline from an actual CI job (or a `CI=1`-tagged run that mirrors the CI fast path) and replace `tests/perf/baseline.json`'s `captured_env`/`rows` with those CI-measured numbers so the CI-gated tier's hard `*1.25` assertion is judged against CI-representative numbers, not this dev sandbox's numbers.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The env-matched gating pattern (captured_env tag + hard-enforce-on-match/advisory-on-mismatch) is established and ready for Plan 07's report-only rows to reuse if useful, though report-only rows are explicitly advisory-only per D-09 and don't need the hard-gate half of this pattern.
- REQ-performance-slos' CI-gated tier is functionally complete; the only open item is swapping in a CI-captured baseline (see Known Limitations above) — this does not block Plan 07 or 08.

---
*Phase: 04-interoperability-performance-verification*
*Completed: 2026-07-28*

## Self-Check: PASSED

- FOUND: tests/perf/test_translate_latency.py
- FOUND: tests/perf/test_execute_overhead.py
- FOUND: tests/perf/baseline.json
- FOUND commit 63c93f6
- FOUND commit 5df0e45
