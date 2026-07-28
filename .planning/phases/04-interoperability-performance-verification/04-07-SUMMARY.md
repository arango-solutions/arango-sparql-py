---
phase: 04-interoperability-performance-verification
plan: 07
subsystem: testing
tags: [perf, pytest, docker-compose, arangodb, rdflib, thread-safety, sparql, latency]

# Dependency graph
requires:
  - phase: 04-interoperability-performance-verification
    provides: "04-01's perf harness (p95/append_report), tests/integration/conftest.py's Docker boot/skip helpers, 04-06's CI-gated D-08 perf tier"
provides:
  - "The D-09 report-only tier of REQ-performance-slos: 6 Docker-gated §9.4 rows (/sparql GET, /schema/introspect cache-miss+cache-hit, memory idle, memory load, concurrency, first-byte) plus the key-gated /nl-translate row, all appending to a checked-in tests/perf/LATENCY_REPORT.md, never CI-gating"
  - "A hardened, reusable Docker-connect skip-gating layer (tests/perf/conftest.py: live_arango_or_skip / arango_seeded_collection / connect_session_or_skip / connect_session_over_socket_or_skip) any future Docker-gated perf row can reuse"
  - "A fix for a real, previously-latent env-pollution race (this repo's dev .env silently overriding ARANGO_URL/ARANGO_DB for the whole tests/perf session) and a defensive lock around rdflib's shared, non-thread-safe SPARQL grammar entry point"
affects: [testing, translate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Docker-gated perf/integration test env resolution must be locked in (os.environ.setdefault) before any module that transitively imports arango_sparql.service — that import fires a no-override load_dotenv() that silently pollutes ARANGO_URL/ARANGO_DB from this repo's dev .env for the remainder of the process"
    - "Report-only (D-09) test rows must skip-gate (pytest.skip) on ArangoDB connect/auth failure, never let it propagate as an ERROR — centralized once in tests/perf/conftest.py rather than duplicated per file"
    - "rdflib's SPARQL grammar (module-level pyparsing ParserElement singletons) is not documented thread-safe; any code path that can be invoked concurrently (this service's FastAPI-threaded /execute) should serialize calls into parse_sparql()"

key-files:
  created:
    - tests/perf/LATENCY_REPORT.md
  modified:
    - tests/perf/conftest.py
    - tests/integration/conftest.py
    - tests/perf/test_sparql_protocol_latency.py
    - tests/perf/test_schema_introspect_latency.py
    - tests/perf/test_memory_idle.py
    - tests/perf/test_memory_load.py
    - tests/perf/test_concurrency.py
    - tests/perf/test_first_byte.py
    - arango_sparql/translate/parser.py

key-decisions:
  - "Locked ARANGO_URL/ARANGO_TEST_DB env defaults at the top of tests/perf/conftest.py (before its eager import of tests.test_service_sparql_routes) rather than restructuring that import — closes the .env-pollution race at its true root cause without touching Plan 01/06 scaffolding"
  - "Centralized Docker connect/auth skip-gating into 4 shared helper functions in tests/perf/conftest.py instead of duplicating try/except blocks across 6 files — new Docker-gated perf rows can reuse them directly"
  - "Swapped test_concurrency.py's pinned query from ASK to SELECT after discovering ASK's boolean AQL result (RETURN LENGTH(...) > 0) is incompatible with /execute's SparqlExecuteResponse.bindings: list[dict] contract against a real ArangoDB — a real, previously-uncaught gap only the fake double in test_execute_overhead.py was masking; documented as a deferred item rather than changing the /execute response contract (out of scope for this hardening pass)"
  - "Added a defensive threading.Lock around parse_sparql()'s parseQuery/translateQuery calls given rdflib's SPARQL grammar has no documented thread-safety guarantee and this service dispatches concurrent /execute requests via FastAPI's thread pool"

requirements-completed: [REQ-performance-slos]

# Metrics
duration: 55min
completed: 2026-07-28
---

# Phase 4 Plan 07: Report-Only Perf Tier (D-09) + Docker-Connect Hardening Summary

**6 Docker-gated §9.4 report rows (sparql GET, schema introspect miss/hit, memory idle/load, concurrency, first-byte) captured into a checked-in LATENCY_REPORT.md, after fixing a real .env-pollution race that made them target the wrong ArangoDB port/database and ERROR instead of skip.**

## Performance

- **Duration:** ~55 min (continuation from Task 1 checkpoint)
- **Started:** 2026-07-28 (continuation session)
- **Completed:** 2026-07-28
- **Tasks:** 1 (Task 1 committed in a prior session at `901ed75`) + checkpoint resolution (hardening fix + report population, this session)
- **Files modified:** 9 (1 created: LATENCY_REPORT.md)

## Accomplishments
- Fixed a real bug: this repo's dev `.env` (`ARANGO_URL=http://localhost:8529`, `ARANGO_DB=_system`) was silently leaking into the whole `tests/perf` session via an eager, transitive `load_dotenv()` import chain, causing every Docker-gated report row to target the wrong port and the forbidden `_system` database.
- Every Docker-gated report row now skip-gates cleanly (never ERRORs) on any ArangoDB connect/auth failure, via 4 new shared helpers in `tests/perf/conftest.py`.
- Ran the 6 Docker-gated rows against a live `docker-compose` ArangoDB three consecutive times with zero flakes; captured all 6 into `tests/perf/LATENCY_REPORT.md`.
- Discovered and fixed a genuine concurrency bug candidate (rdflib's SPARQL grammar has no documented thread-safety guarantee) with a defensive lock in `arango_sparql/translate/parser.py`.
- Discovered (and worked around, not fixed) a real, previously-uncaught `/execute` gap: ASK queries translate to a scalar boolean AQL result that the endpoint's dict-list response contract can't represent against a real ArangoDB — documented as a deferred item.
- `/nl-translate` correctly skip-gates on the absent `NL2SPARQL_API_KEY` (never read/logged); noted as "not captured" in the report with the exact command to capture it later.
- Confirmed no secret/API key appears anywhere in the committed `LATENCY_REPORT.md`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author the 7 report-only perf rows (non-gating)** - `901ed75` (feat) — prior session
2. **Checkpoint pause record** - `cea4cfa` (docs) — prior session

**Hardening fix (this session):**
3. **Fix connect/auth skip-gating + `.env`-pollution race + concurrency query + parser lock** - `06ddb37` (fix)
4. **Populate LATENCY_REPORT.md from Docker-gated rows** - `86272e3` (docs)

**Plan metadata:** (this commit, below)

## Files Created/Modified
- `tests/perf/conftest.py` - env-pollution-preemption guard (locks `ARANGO_URL`/`ARANGO_TEST_DB` before the eager `test_service_sparql_routes` import that triggers `load_dotenv()`); new shared helpers `live_arango_or_skip`, `arango_seeded_collection`, `connect_session_or_skip`, `connect_session_over_socket_or_skip`
- `tests/integration/conftest.py` - unconditional `_system` → `sparql-to-aql` coercion on `DEFAULT_ARANGO_DB`, regardless of which env var it resolved from
- `tests/perf/test_sparql_protocol_latency.py`, `test_schema_introspect_latency.py`, `test_memory_idle.py`, `test_memory_load.py`, `test_first_byte.py` - delegate to the shared skip-gating helpers instead of duplicated fixture bodies
- `tests/perf/test_concurrency.py` - swapped pinned `ASK` query for a pinned `SELECT` (see Decisions); delegates to shared helpers
- `arango_sparql/translate/parser.py` - `threading.Lock()` around `parseQuery`/`translateQuery` in `parse_sparql()`
- `tests/perf/LATENCY_REPORT.md` - checked-in, populated latency report (6 rows captured, 1 noted not-captured)

## Decisions Made
See `key-decisions` in frontmatter above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking / Rule 1 - Bug] `.env` pollution silently broke every Docker-gated report row's ArangoDB target**
- **Found during:** Checkpoint resolution, first attempt at running the Docker report rows
- **Issue:** `tests/perf/conftest.py`'s eager import of `tests.test_service_sparql_routes` transitively imports `arango_sparql.service`, whose module-level `load_dotenv()` (no override) filled in `ARANGO_URL=http://localhost:8529` (this project's dev port, not the docker-compose test container's host port 8532) and `ARANGO_DB=_system` (forbidden for tests) whenever those vars were unset — before `tests/integration/conftest.py` ever computed its own `DEFAULT_ARANGO_*` constants. This surfaced as a `401 not authorized` `DatabaseListError` ERROR (not a skip) at fixture setup.
- **Fix:** Lock in test-safe `ARANGO_URL`/`ARANGO_TEST_DB` defaults via `os.environ.setdefault(...)` at the very top of `tests/perf/conftest.py`, before the vulnerable import. Added an unconditional `_system` coercion in `tests/integration/conftest.py` as a second, independent layer of defense. Wrapped every ArangoDB connect/auth touchpoint in the 6 Docker-gated files in shared `pytest.skip()`-on-failure helpers.
- **Files modified:** `tests/perf/conftest.py`, `tests/integration/conftest.py`, all 6 Docker-gated `tests/perf/test_*.py` files
- **Verification:** `ARANGO_TEST_DB=sparql-to-aql ARANGO_USER=root ARANGO_PASSWORD=rootpw RUN_INTEGRATION=1 python -c "import tests.perf.conftest as pc; print(pc.DEFAULT_ARANGO_URL, pc.DEFAULT_ARANGO_DB)"` now prints `http://localhost:8532 sparql-to-aql`; without Docker, `pytest tests/perf -m perf -q` shows 7 clean skips, 0 errors.
- **Commit:** `06ddb37`

**2. [Rule 1 - Bug] `test_concurrency.py`'s pinned `ASK` query 500s against a real ArangoDB**
- **Found during:** Checkpoint resolution, running the Docker report rows for the first time
- **Issue:** `tests/translate/ask.yml` documents that `ASK` translates to `RETURN LENGTH(...) > 0`, a scalar boolean AQL cursor result. `/execute`'s `SparqlExecuteResponse.bindings: list[dict]` response model cannot represent a bare boolean, causing a `pydantic_core.ValidationError` under every concurrent call. This was previously masked entirely because `test_execute_overhead.py`'s fake ArangoDB double ignores the AQL text and always returns a fixed dict row.
- **Fix:** Swapped the pinned query from `ASK { ?s a :PerfConcurrencyThing }` to `SELECT ?s WHERE { ?s a :PerfConcurrencyThing }` — the same shape every sibling Docker-gated report row already uses successfully. Did **not** change `/execute`'s response contract (that is a separate, out-of-scope architectural question — see Known Gaps below).
- **Files modified:** `tests/perf/test_concurrency.py`
- **Verification:** `test_concurrency_p95_no_error_budget_burn` passes reliably across 3 consecutive standalone runs and within the full 6-row Docker battery.
- **Commit:** `06ddb37`

**3. [Rule 1 - Bug, defensive] Serialized `parse_sparql()`'s rdflib calls behind a lock**
- **Found during:** Investigating the same failure window as deviation #2 (an intermittent `<lambda>() missing 1 required positional argument: 'x'` error surfaced once from a different file when run in the same session as the then-broken concurrency row)
- **Issue:** rdflib's SPARQL grammar (`rdflib.plugins.sparql.parser`) is built on module-level singleton pyparsing `ParserElement` objects with no documented thread-safety guarantee for concurrent `parseQuery` calls from multiple threads. This service dispatches concurrent `/execute`/`/sparql`/`/translate` requests via FastAPI's thread pool, so concurrent real traffic is the expected case, not an edge case.
- **Fix:** Added a module-level `threading.Lock()` around the `parseQuery`/`translateQuery` calls in `arango_sparql/translate/parser.py`'s `parse_sparql()` — the single canonical SPARQL-parsing entry point every route uses.
- **Files modified:** `arango_sparql/translate/parser.py`
- **Verification:** Full non-regression suite (`pytest -m "not integration and not w3c and not eval and not perf" -q`) still green (1428 passed); the 6-row Docker battery passed 3/3 consecutive runs post-fix.
- **Commit:** `06ddb37`

---

**Total deviations:** 3 auto-fixed (1 blocking/bug — env-pollution race; 1 bug — concurrency row's own query choice; 1 defensive bug fix — parser thread-safety)
**Impact on plan:** All three were necessary to make the Docker-gated report rows actually run against a real ArangoDB and produce trustworthy numbers — the plan's stated goal. No scope creep into `/execute`'s response contract (see Known Gaps).

## Known Gaps (not fixed — out of scope for this hardening pass)

- **`/execute` cannot represent an ASK query's boolean AQL result.** `tests/translate/ask.yml` confirms ASK legitimately translates to `RETURN LENGTH(...) > 0` (a scalar boolean), but `SparqlExecuteResponse.bindings: list[dict]` has no shape for that — a real request with an ASK query against `/execute` today returns a 500 (unhandled `pydantic_core.ValidationError`) against a real ArangoDB. This was invisible until this plan's Docker-gated concurrency row was the first test in the suite to send an ASK query to `/execute` against a real backend (every prior ASK-via-`/execute` test used the fake double, which ignores AQL text entirely). Recommend a dedicated follow-up: either extend `SparqlExecuteResponse` to support a boolean-result variant, or have `/execute` raise a typed `UnsupportedSparqlError` for ASK (mirroring CLAUDE.md's "surface unsupported SPARQL early" mandate) until proper support lands.
- **Pre-existing, unrelated environment gap:** `tests/integration/test_sparqlwrapper_smoke.py`'s two tests fail in this sandbox with `ModuleNotFoundError: No module named 'SPARQLWrapper'` — the optional `SPARQLWrapper` package isn't installed here. Untouched by this plan; not a regression (confirmed pre-existing, unrelated to any file this plan modified).

## Issues Encountered
None beyond the deviations documented above (each investigated and resolved inline during the checkpoint-resolution session).

## User Setup Required
None - no external service configuration required. (Docker + optional `NL2SPARQL_API_KEY` remain human-run, on-demand, exactly as designed by this plan — not a one-time setup step.)

## Next Phase Readiness
- REQ-performance-slos is now fully delivered across both tiers: D-08 (CI-gated, `04-06`) and D-09 (report-only, this plan) cover all 11 §9.4 rows.
- `tests/perf/LATENCY_REPORT.md` holds 6 measured rows; `nl_translate_p95_ms` remains uncaptured pending a human-supplied `NL2SPARQL_API_KEY` — re-run `RUN_INTEGRATION=1 NL2SPARQL_API_KEY=... pytest tests/perf/test_nl_latency.py -m perf -q` at any time to fill it in.
- The `/execute` ASK-boolean-result gap (Known Gaps above) is a legitimate small follow-up for a future plan; it does not block Phase 4 completion since D-09 rows are advisory-only and the workaround (pinning a SELECT) is itself a documented, defensible choice.

---
*Phase: 04-interoperability-performance-verification*
*Completed: 2026-07-28*
