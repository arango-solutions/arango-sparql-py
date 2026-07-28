---
phase: 04-interoperability-performance-verification
plan: 04
subsystem: testing
tags: [rdflib, owl, rdf-xml, isomorphism, schema-cache, sparql-protocol, integration-test, docker]

# Dependency graph
requires:
  - phase: 04-02
    provides: RDF/XML format-dispatch on /mapping/import-owl and /mapping/export-owl (turtle_to_mapping/mapping_to_turtle format= kwarg), unblocking this plan's RDF/XML isomorphism row
provides:
  - "tests/integration/test_aoe_roundtrip.py: Docker-gated AOE own-half contract test proving REQ-ontoextract-integration (D-03/D-04) with no external arango-ontoextract service"
  - "Turtle and RDF/XML export-owl -> import-owl triple-bag isomorphism assertions (rdflib.Graph.isomorphic, blank-node-safe)"
  - "SchemaCache.put() deterministic-activation pattern proven end-to-end: imported OWL -> queryable /sparql (ASK true/false + SELECT bindings) against seeded docker-compose ArangoDB"
affects: [04-05-ontology-playground-roundtrip, 04-06-perf-suite]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "rdflib.Graph.isomorphic() as the blank-node-safe triple-bag equality check for OWL round-trip contract tests (RESEARCH.md Pattern 1), reused verbatim from the 04-RESEARCH.md sketch"
    - "SchemaCache.put(db_name, bundle) direct injection to deterministically activate an imported mapping for /sparql, bypassing heuristic/analyzer auto-detection (RESEARCH.md Pattern 2)"

key-files:
  created:
    - tests/integration/test_aoe_roundtrip.py
  modified: []

key-decisions:
  - "Both plan tasks (Turtle+RDF/XML isomorphism, and SchemaCache activation + ASK/SELECT) landed in a single commit/file since the isomorphism assertions and the queryability assertions share the same fixture, connect helper, and import/export helpers with no natural task boundary in the diff — mirrors 04-02's precedent of combining tightly-coupled tasks."
  - "Fixture uses a distinct collection name (AoePerson) and IRI namespace (example.org/aoe#) rather than reusing test_execute_endpoint.py's bare Person/example.org# fixture verbatim, so this file's seeded collection and this file's SchemaCache.put() entry never collide with that module's own fixtures when both run in the same RUN_INTEGRATION=1 session."
  - "The Turtle isomorphism assertion is trivially true by construction (mapping_to_turtle returns bundle.owl_turtle verbatim on a Turtle->Turtle round trip per owl.py's documented fast path) — still a valid and necessary proof of the contract; the RDF/XML row is the one that genuinely exercises reparse+reserialize round-trip fidelity end-to-end through the route layer."

requirements-completed: [REQ-ontoextract-integration]

# Metrics
duration: 25min
completed: 2026-07-28
---

# Phase 04 Plan 04: AOE own-half roundtrip contract test Summary

**Docker-gated `tests/integration/test_aoe_roundtrip.py` proves our `/mapping/import-owl` <-> `/mapping/export-owl` OWL fidelity (Turtle + RDF/XML, `rdflib.Graph.isomorphic()`) and end-to-end `/sparql` queryability via `SchemaCache.put()` deterministic activation — with zero external `arango-ontoextract` service involved.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-28T16:10:00Z
- **Completed:** 2026-07-28T16:35:00Z
- **Tasks:** 2 (1 commit — see Deviations)
- **Files modified:** 1 (new file)

## Accomplishments

- `tests/integration/test_aoe_roundtrip.py` proves REQ-ontoextract-integration's own-half contract (D-03/D-04): a `phys:`-annotated OWL fixture (`_AOE_PERSON_ONTOLOGY_TTL`, extending the proven `_PERSON_ONTOLOGY_TTL` shape from `tests/integration/test_execute_endpoint.py`) round-trips through `POST /mapping/import-owl` -> `POST /mapping/export-owl` with `rdflib.Graph.isomorphic()` triple-bag equality for both Turtle (`Accept: text/turtle`) and RDF/XML (`Accept: application/rdf+xml`) — the RDF/XML row exercises the format-dispatch plumbing Plan 04-02 landed.
- After import, `_resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)` deterministically activates the mapping for `/sparql` (import-owl is stateless per RESEARCH.md Pattern 2 — there is no automatic wiring from "imported this OWL" to "the protocol endpoint sees it"). A seeded two-row `AoePerson` collection then proves both an `ASK` `true` case, an `ASK` `false` case, and a `SELECT` returning well-formed bindings matching the seeded rows.
- The whole file is gated behind the `integration` marker + `RUN_INTEGRATION=1` (mirroring the existing convention) and skips cleanly with no Docker: `pytest -m integration tests/integration/test_aoe_roundtrip.py -q` -> `3 skipped` with no ArangoDB running.
- Verified green against a live docker-compose ArangoDB (host 8532, DB `sparql-to-aql`): `RUN_INTEGRATION=1 pytest -m integration tests/integration/test_aoe_roundtrip.py -q` -> `3 passed in 8.98s`.
- Full non-regression suite green: `pytest -m "not integration and not w3c and not eval and not perf" -q` -> `1428 passed` (unchanged from the 04-02 baseline); `RUN_INTEGRATION=1 pytest tests/integration tests/cross -q` -> `128 passed` (no interference with sibling integration/cross-validation suites sharing the process-wide `SchemaCache` singleton).

## Task Commits

Both tasks landed in a single commit (see Deviations for rationale):

1. **Task 1 + Task 2: AOE roundtrip contract test (isomorphism + SchemaCache activation)** - `2ddea58` (test)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `tests/integration/test_aoe_roundtrip.py` - New Docker-gated integration test: `_AOE_PERSON_ONTOLOGY_TTL` fixture, `_live_arango`/`_seeded_collection` fixtures (shared boot/skip helpers imported from `tests.integration.conftest`), `_connect_session`/`_import_owl`/`_export_owl` helpers, two isomorphism tests (Turtle, RDF/XML) and one `SchemaCache.put()` + ASK/SELECT queryability test.

## Decisions Made

- **Single combined commit for both tasks:** the isomorphism assertions (Task 1) and the queryability assertions (Task 2) share the same fixture, `_connect_session` helper, and `_import_owl`/`_export_owl` helpers with no clean line-level split — writing the file once as a coherent whole and committing it in one pass avoided an artificial two-pass diff with no review benefit, mirroring the same rationale 04-02's SUMMARY documented for its own combined commits.
- **Distinct fixture namespace (`AoePerson` / `example.org/aoe#`):** kept separate from `test_execute_endpoint.py`'s `Person` / `example.org/` fixture so this file's seeded collection and `SchemaCache.put()` entry (keyed by `db_name` only, process-wide) never collide with that module's state when both integration files run in the same `RUN_INTEGRATION=1` pytest session.
- **`SchemaCache.put()` over auto-detection:** per RESEARCH.md's explicit recommendation, used direct cache injection (deterministic) rather than seeding real collections and waiting for heuristic/analyzer auto-detection to rediscover the schema — the AOE contract is specifically about the *imported OWL* being queryable, not about proving auto-detection.

## Deviations from Plan

### Auto-fixed Issues

None — the plan's two tasks were implementable directly from the RESEARCH.md sketches and the 04-02 format-dispatch work already in place; no bugs, missing functionality, or blocking issues were discovered during execution.

---

**Total deviations:** 0 auto-fixed. One documented commit-structuring choice (both tasks combined into a single commit) — see Decisions Made above, not a Rule 1-4 deviation since no code behavior was added/changed beyond the plan's literal scope.
**Impact on plan:** None — plan executed as written; the combined-commit choice is a mechanical packaging decision, not a scope change.

## Issues Encountered

None. Docker was available in this session (`docker info` succeeded), so both the "skips cleanly without Docker" path (verified by running without `RUN_INTEGRATION=1`) and the "runs green with ArangoDB up" path (verified with `RUN_INTEGRATION=1`) were both directly exercised rather than one being assumed from code inspection alone.

## User Setup Required

None - no external service configuration required. Docker/docker-compose is the only runtime dependency, already covered by the existing `tests/integration/conftest.py` boot/skip convention.

## Next Phase Readiness

- REQ-ontoextract-integration is now proven end-to-end for our own half of the contract (import/export fidelity + queryability); no further AOE-related work is anticipated for this phase.
- Plan 04-05 (Ontology Playground roundtrip) can proceed independently — it uses the vendored `cosmic_coffee.rdf` fixture (no `phys:` annotations, file-based only, no live SPARQL), deliberately kept separate from this plan's `phys:`-annotated fixture per Pitfall 3.
- No blockers for the next wave.

---
*Phase: 04-interoperability-performance-verification*
*Completed: 2026-07-28*

## Self-Check: PASSED

All claimed files exist and the claimed commit hash (`2ddea58`) resolves in `git log`.
