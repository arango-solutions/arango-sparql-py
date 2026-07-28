# Phase 04 — Deferred Items

Out-of-scope discoveries logged during plan execution (not fixed, per the
executor's SCOPE BOUNDARY rule — only issues directly caused by the current
task's own changes are auto-fixed).

## 04-07 Task 1

- **Pre-existing CI-gated perf flake (Plan 06 files, unrelated to 04-07).**
  `tests/perf/test_translate_latency.py::test_translate_cold_p95` /
  `test_translate_warm_p95` and `tests/perf/test_execute_overhead.py::test_execute_overhead_p95`
  intermittently fail locally (`p95` running ~1.3-2.6x `baseline * 1.25`) when
  run repeatedly in this sandbox. This is already documented in
  `04-06-SUMMARY.md`'s "Issues Encountered" / "Known Limitations" sections as
  environmental jitter in this specific interactive dev sandbox, expected to
  resolve once an authoritative `captured_env: "ci"` baseline replaces the
  current interim `captured_env: "local"` bootstrap baseline. Verified this
  session: reran 3x, failures are non-deterministic (sometimes 0/3, sometimes
  2/3, sometimes 3/3 fail) and always in `test_translate_latency.py`/
  `test_execute_overhead.py` (Plan 06 files) — never in any of 04-07's own
  7 new report-only files, which never assert against a budget. Not fixed
  here: out of scope for 04-07 (no files in this plan's `files_modified` list
  touch the CI-gated tier), and the follow-up (capture a CI-representative
  baseline) is already tracked as 04-06's own open item.
- **`ruff check` findings in pre-existing Plan 01/06 files (not introduced
  this plan).** `tests/perf/conftest.py` has an unsorted import block
  (`I001`); `tests/perf/test_execute_overhead.py` has an `F811` redefinition
  of the `fake_client_factory` fixture name as a test parameter. Neither file
  is in 04-07's `files_modified` list. Not fixed here — logged for a future
  lint-cleanup pass.
