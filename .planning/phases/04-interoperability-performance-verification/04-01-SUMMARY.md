---
phase: 04-interoperability-performance-verification
plan: 01
subsystem: testing
tags: [pytest, perf, sparqlwrapper, rdflib, fixtures, docs]

# Dependency graph
requires: []
provides:
  - "perf pytest marker registered in pyproject.toml (CI-blocking p95 gate)"
  - "SPARQLWrapper>=2.0.0 dev dependency + refreshed uv.lock"
  - "tests/perf/ importable package with reused _FakeArangoClient double + p95/load_baseline/append_report helpers"
  - "tests/fixtures/cosmic_coffee.rdf vendored MIT fixture with pinned-SHA NOTICE"
  - "docs/howto/ directory anchor (index.md)"
affects: [04-02, 04-05, 04-06, 04-07, 04-08]

# Tech tracking
tech-stack:
  added: ["SPARQLWrapper>=2.0.0 (dev dep)"]
  patterns:
    - "Perf test doubles re-exported (not duplicated) from tests/test_service_sparql_routes.py for a single source of truth"
    - "Vendored third-party fixtures pinned to a commit SHA with a NOTICE.md provenance file (mirrors tests/nl2sparql/eval/vendored/*/NOTICE.md)"

key-files:
  created:
    - tests/perf/__init__.py
    - tests/perf/conftest.py
    - tests/fixtures/cosmic_coffee.rdf
    - tests/fixtures/cosmic_coffee.NOTICE.md
    - docs/howto/index.md
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "conftest.py imports (does not copy) _FakeArangoClient/_FakeDb/_FakeCursor/fake_client_factory/_connect_session from tests.test_service_sparql_routes — the import path resolves cleanly (tests/__init__.py exists), so no ~140-line duplication was needed"
  - "cosmic_coffee.rdf pinned to commit 9a0eb93cef978b1ee6c4a6857dc0ce2733444ea0 (last commit touching that path on main), MIT license verified via GitHub API repo endpoint"

patterns-established:
  - "p95(samples) -> statistics.quantiles(sorted(samples), n=100)[93], stdlib-only, no pytest-benchmark/numpy/scipy"
  - "load_baseline()/append_report() mirror the tests/nl2sparql/eval/baseline.json checked-in-baseline convention for the perf suite"

requirements-completed: []  # REQ-performance-slos and REQ-thirdparty-tool-compat are foundational-only here; full completion tracked in later Phase-4 plans (06/07/05/08)

# Metrics
duration: ~10min
completed: 2026-07-28
---

# Phase 04 Plan 01: Wave-0 Foundation Scaffolding Summary

Registered the `perf` pytest marker and `SPARQLWrapper` dev dependency, scaffolded `tests/perf/` reusing the proven `_FakeArangoClient` double plus stdlib p95/baseline/report helpers, vendored the MIT-licensed `cosmic-coffee.rdf` Ontology-Playground fixture with a pinned-SHA NOTICE, and created the `docs/howto/` directory anchor — unblocking every downstream Phase-4 plan (05, 06, 07, 08).

## Performance

- **Duration:** ~10 min
- **Tasks:** 3 completed
- **Files modified:** 7 (2 modified, 5 created)

## Accomplishments
- `perf` marker registered cleanly (verified: `pytest -m perf --collect-only -q` emits no unregistered-marker warning); `legacy_roundtrip`/`bench` markers correctly NOT added per D-01/D-02 and RESEARCH.md Pitfall 4.
- `SPARQLWrapper>=2.0.0` added to `[dev]` optional-dependencies and `uv lock` refreshed (`uv.lock` now carries a `sparqlwrapper` entry).
- `tests/perf/` is a real importable package: `conftest.py` re-exports the existing `_FakeArangoClient`/`_FakeDb`/`_FakeCursor`/`fake_client_factory`/`_connect_session` (no duplication — single source of truth stays in `tests/test_service_sparql_routes.py`) and adds three new stdlib-only helpers (`p95`, `load_baseline`, `append_report`).
- `tests/fixtures/cosmic_coffee.rdf` vendored verbatim (26,981 bytes / 349 triples, matching RESEARCH.md's session-verified counts exactly: 6 `owl:Class`, 7 `owl:ObjectProperty`, 36 `owl:DatatypeProperty`), pinned to commit `9a0eb93cef978b1ee6c4a6857dc0ce2733444ea0` with an MIT-license NOTICE mirroring the `tests/nl2sparql/eval/vendored/ck25/NOTICE.md` convention.
- `docs/howto/index.md` created, anchoring the new directory and listing the 5 planned recipe files (protege, yasgui, arq, sparqlwrapper, ontology-playground).
- Full non-regression suite (`pytest -m "not integration and not w3c and not eval and not perf" -q`) stays green: 1405 passed, 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Register the perf marker and add SPARQLWrapper dev dependency** - `06cb77d` (feat)
2. **Task 2: Scaffold tests/perf package with reused fake double and stdlib helpers** - `abf7e33` (feat)
3. **Task 3: Vendor cosmic_coffee.rdf with NOTICE and create docs/howto index** - `ab01aff` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `pyproject.toml` - Added `perf` marker to `[tool.pytest.ini_options] markers`; added `SPARQLWrapper>=2.0.0` to `[project.optional-dependencies].dev`
- `uv.lock` - Refreshed to include the resolved `sparqlwrapper` (2.0.0) entry
- `tests/perf/__init__.py` - Empty package marker (mirrors `tests/cross/__init__.py`)
- `tests/perf/conftest.py` - Re-exports the fake ArangoDB double + connect helper; defines `p95`/`load_baseline`/`append_report`
- `tests/fixtures/cosmic_coffee.rdf` - Vendored MS Ontology Playground "cosmic-coffee" RDF/XML fixture (349 triples, MIT)
- `tests/fixtures/cosmic_coffee.NOTICE.md` - Provenance notice: source, pinned commit SHA, MIT license, downstream use
- `docs/howto/index.md` - `docs/howto/` directory anchor + recipe index table

## Decisions Made
- Reused the `import` path for the fake double (`from tests.test_service_sparql_routes import ...`) rather than copying the ~140-line block verbatim, since `tests/__init__.py` already makes the module cleanly importable — verified directly before writing `conftest.py`. This keeps a single source of truth for the double's behavior.
- Pinned `cosmic_coffee.rdf` to commit `9a0eb93cef978b1ee6c4a6857dc0ce2733444ea0` (the actual last-touch commit for that file's path on `main`, resolved via the GitHub API `commits` endpoint) rather than whatever `main` currently resolves to, per the plan's "pin to a commit SHA" security requirement (T-04-01).
- `requirements-completed` left empty in this plan's frontmatter: both `REQ-performance-slos` and `REQ-thirdparty-tool-compat` are multi-plan requirements: this plan only lands the Wave-0 scaffolding they depend on (marker, dev dep, fake-double reuse, vendored fixture, docs anchor), not the test bodies themselves (Plans 05/06/07/08 own those). Marking them complete here would be premature.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' automated verification commands passed on first attempt; no Rule 1-4 auto-fixes were needed.

## Known Stubs

None. This plan is pure scaffolding (config + test infra + a vendored fixture + a docs index) with no UI/data-rendering surface, so the stub-scan criteria (hardcoded empty values flowing to rendering, placeholder text, unwired data sources) do not apply.

## Threat Flags

None beyond what the plan's own `<threat_model>` already anticipated and mitigated (T-04-01 pinned-SHA vendoring, T-04-02/T-04-SC SPARQLWrapper supply-chain — both closed as designed: SHA pinned, `uv.lock` records the resolved hash, no live fetch at test time).

## Self-Check: PASSED

- FOUND: pyproject.toml (perf marker + SPARQLWrapper dep present)
- FOUND: uv.lock (sparqlwrapper entry present, 3 occurrences)
- FOUND: tests/perf/__init__.py
- FOUND: tests/perf/conftest.py (108 lines, exceeds min_lines: 60)
- FOUND: tests/fixtures/cosmic_coffee.rdf (26,981 bytes, 349 triples verified via rdflib)
- FOUND: tests/fixtures/cosmic_coffee.NOTICE.md
- FOUND: docs/howto/index.md
- FOUND commit 06cb77d
- FOUND commit abf7e33
- FOUND commit ab01aff
