# Latency Report

Checked-in, human-reviewed perf artifact (D-09). Report-only rows never gate CI; see PRD §9.4 for the full SLO table.

| Row | p95 (ms) | Budget (ms) | Status |
|---|---|---|---|
| concurrency_p95_ms | 52.640 | - | report-only |
| first_byte_p95_ms | 12.338 | 200.0 | OK |
| memory_idle_rss_mib_p95 | 147.875 | 250.0 | OK |
| memory_load_rss_mib_p95 | 202.425 | 1536.0 | OK |
| schema_introspect_cache_miss_p95_ms | 22.238 | 2500.0 | OK |
| schema_introspect_cache_hit_p95_ms | 0.000 | 15.0 | OK |
| sparql_get_p95_ms | 62.838 | 150.0 | OK |

## Not Captured

- `nl_translate_p95_ms` (`/nl-translate`, live LLM, PRD §9.4 target p95 ≤ 3.5s) —
  skipped: no `NL2SPARQL_API_KEY` was supplied for this run (the key is
  human-held and never provided to CI/the executing agent per T-04-13).
  Run `RUN_INTEGRATION=1 NL2SPARQL_API_KEY=... pytest tests/perf/test_nl_latency.py -m perf -q`
  with your own key to capture this row; append the resulting measurement
  here by hand or re-run the suite (never commit the key itself).

## Measurement Notes

- Captured against a local single-node `docker-compose` ArangoDB (host port
  8532), not a production cluster — see each row's module docstring for any
  documented scale-down from the PRD's illustrative concurrency figures.
- `concurrency_p95_ms` has no CI-blocking budget (report-only, D-09); the row's
  own "no error budget burn" invariant (every concurrent call must return 200)
  is asserted directly by the test and passed.
