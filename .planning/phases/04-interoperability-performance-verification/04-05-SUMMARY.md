---
phase: 04-interoperability-performance-verification
plan: 05
subsystem: testing
tags: [sparqlwrapper, uvicorn, rdflib, owl, rdf-xml, w3c-protocol, docker-gated]

# Dependency graph
requires:
  - phase: 04-01
    provides: SPARQLWrapper dev dependency + vendored cosmic_coffee.rdf fixture
  - phase: 04-02
    provides: RDF/XML Content-Type/Accept negotiation on /mapping/import-owl and /mapping/export-owl
provides:
  - "tests/integration/test_sparqlwrapper_smoke.py — real SPARQLWrapper client driving SELECT + ASK + Service Description over a background uvicorn socket"
  - "tests/integration/test_ontology_playground_roundtrip.py — cosmic_coffee.rdf RDF/XML isomorphic roundtrip through /mapping routes"
  - "Automated half of REQ-thirdparty-tool-compat (D-06) proven Docker-gated"
affects: [04-06, 04-07, 04-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Background uvicorn.Server bound to 127.0.0.1:0 in a daemon thread + a real-HTTP readiness poll (not just server.started) before firing client requests — the standard pattern for giving a genuine urllib-based client (SPARQLWrapper) a real socket, since FastAPI's in-process ASGI transport never opens one"
    - "SchemaCache.put() direct injection for deterministic /sparql queryability, reusing the 04-04 AOE-roundtrip pattern rather than depending on heuristic/analyzer auto-detection"
    - "Every HTTP call (including /connect) travels over the real bound socket via stdlib urllib — no in-process test transport anywhere in the SPARQLWrapper smoke file, keeping the anti-pattern (SPARQLWrapper -> in-process transport) impossible to accidentally reintroduce"

key-files:
  created:
    - tests/integration/test_sparqlwrapper_smoke.py
    - tests/integration/test_ontology_playground_roundtrip.py
  modified: []

key-decisions:
  - "SPARQLWrapper smoke test's /connect call goes over the real bound socket via urllib.request (not FastAPI's in-process ASGI test transport) — even though /connect's session-token side effect would work identically in-process (same Python process, same module-global _sessions dict), keeping every HTTP call in this file on the wire makes the file's own anti-pattern guard (no in-process transport anywhere) trivially self-enforcing rather than relying on a human to notice a mixed-mode file later"
  - "Reused the 04-04 AOE-roundtrip's SchemaCache.put()-direct-injection pattern for schema activation rather than seeding a collection and hoping heuristic auto-detection resolves it identically — deterministic and already proven"
  - "Dedicated SparqlwrapperPerson collection + http://example.org/sw# namespace (distinct from test_execute_endpoint.py's Person and test_aoe_roundtrip.py's AoePerson) so this file's seeded data and process-wide SchemaCache entry never collide with sibling integration files in the same RUN_INTEGRATION=1 pytest session"
  - "Ontology Playground roundtrip imports/exports via the mapping wire-dict path (not the ontology_ttl round-trip path) — proven by the 04-04 AOE test to preserve the full owl_turtle serialization (all triples, including annotations outside the entities/relationships shape), which is what isomorphism against a general catalogue fixture like cosmic_coffee.rdf requires"

patterns-established:
  - "Readiness wait beyond uvicorn.Server.started: poll a real HTTP GET against the bound port until it succeeds (not just check the started flag) before handing the port to a real client, closing the accept-loop startup race the plan called out"

requirements-completed: [REQ-thirdparty-tool-compat]

# Metrics
duration: ~20min
completed: 2026-07-28
---

# Phase 04 Plan 05: SPARQLWrapper + Ontology Playground automated smoke tests Summary

**A real `SPARQLWrapper` client (genuine `urllib` HTTP) drives SELECT, ASK, and an unauthenticated Service Description fetch against `/sparql` over a background `uvicorn` server bound to a real ephemeral socket, and the vendored MIT `cosmic_coffee.rdf` fixture round-trips `application/rdf+xml` through `/mapping/import-owl` → `/mapping/export-owl` with `rdflib.Graph.isomorphic()` equality — both Docker-gated, closing the automated half of REQ-thirdparty-tool-compat (D-06).**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 completed
- **Files modified:** 2 (both new)

## Accomplishments

- `tests/integration/test_sparqlwrapper_smoke.py`: a module-scoped `uvicorn.Server` bound to `127.0.0.1:0` runs in a daemon thread; the fixture waits on `server.started` and then polls a real HTTP GET against the bound port until it actually answers (closing the accept-loop startup race the plan flagged), before ever handing the port to a client. A dedicated `SparqlwrapperPerson` collection (distinct namespace/name from every other integration file's fixture) is seeded, and its bundle is activated deterministically via `SchemaCache.put()` (the 04-04 AOE-roundtrip pattern) so `/sparql` resolves without depending on heuristic auto-detection. Every HTTP call in the file — including `/connect` — travels over the real bound socket via `urllib.request`; there is no in-process ASGI test transport anywhere in the file, which is also what the plan's own automated verification grep enforces. `SPARQLWrapper` (`setMethod(POST)`, `setReturnFormat(JSON)`, `addCustomHttpHeader("Authorization", ...)`) drives a SELECT (asserting non-empty, name-matching `results.bindings`) and two ASKs (asserting a real Python `bool` under `boolean`, once `True` and once `False`). A separate unauthenticated `GET /sparql` (no `query` param) proves the Service Description document is served as `text/turtle` over the wire.
- `tests/integration/test_ontology_playground_roundtrip.py`: imports the vendored `cosmic_coffee.rdf` (349 triples, MIT) via `POST /mapping/import-owl` with `Content-Type: application/rdf+xml`, re-exports the returned mapping wire dict via `POST /mapping/export-owl` with `Accept: application/rdf+xml`, and asserts `rdflib.Graph.isomorphic()` blank-node-safe equality against the original fixture — plus a companion triple-count sanity check via the `x-triple-count` response header. Pure OWL fidelity only: no `/sparql` query, no `phys:` annotations, kept strictly separate from the AOE contract fixture per 04-RESEARCH.md Pitfall 3.
- Both files skip cleanly (`3 skipped` / `2 skipped`) without Docker, and both went fully green (`5 passed`) against a live docker-compose ArangoDB (host 8532, DB `sparql-to-aql`) in this session.
- Full non-regression suite (`pytest -m "not integration and not w3c and not eval and not perf" -q`) stays green: 1428 passed, 0 failed — identical count to 04-02's post-change baseline, confirming zero unintended side effects.
- `SPARQLWrapper` was already declared in `pyproject.toml`'s `[dev]` extra and `uv.lock` by 04-01 (approved in 04-RESEARCH.md's package-legitimacy audit); this plan only needed `uv sync` to install it (plus the other already-declared/`nl`/`dense` extras that had drifted out of the local venv) into the working environment — no new dependency declarations, no `pyproject.toml`/`uv.lock` diff.

## Task Commits

Each task was committed atomically:

1. **Task 1: SPARQLWrapper smoke over a background uvicorn server** - `a19bea9` (feat)
2. **Task 2: Ontology Playground file-based RDF/XML roundtrip** - `2ed09f3` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `tests/integration/test_sparqlwrapper_smoke.py` - Real SPARQLWrapper client over a background uvicorn socket; SELECT + ASK + Service Description, Docker-gated
- `tests/integration/test_ontology_playground_roundtrip.py` - cosmic_coffee.rdf RDF/XML isomorphic roundtrip through `/mapping/import-owl`/`export-owl`, Docker-gated

## Decisions Made

- Kept the SPARQLWrapper smoke test's `/connect` call on the real bound socket rather than taking the cheaper in-process shortcut (which would have worked functionally, since `/connect` mutates a module-global `_sessions` dict shared by every entry point into the same process) — this makes the file's own "no in-process transport" invariant self-evident from a straight read, matching the plan's automated verification grep and the spirit of the anti-pattern warning in 04-RESEARCH.md Pattern 4.
- Reused `SchemaCache.put()` direct injection (04-04's proven pattern) instead of re-deriving heuristic auto-detection behavior for a bare seeded collection with no `type`/`label` discriminator field — deterministic, avoids depending on the heuristic detector's exact IRI-construction scheme.
- Ontology Playground roundtrip round-trips through the `mapping` wire-dict path (not `ontology_ttl`), matching 04-04's proven RDF/XML isomorphism precedent — the wire dict carries the re-serialized `owl_turtle` field (the *entire* parsed graph, not just the entities/relationships extracted shape), which is what full-fidelity isomorphism against a general catalogue ontology like `cosmic_coffee.rdf` (with annotation/versioning triples beyond bare Class/Property declarations) requires.

## Deviations from Plan

None - plan executed exactly as written. Both automated verification commands passed; no Rule 1-4 auto-fixes were needed in the test code itself.

One environment-setup step beyond the plan's literal text: the local `.venv` was missing `SPARQLWrapper` and several `nl`/`dense`-extra packages (torch, sentence-transformers, arango-query-core, etc.) that a prior session's environment had installed but the current venv didn't reflect. Ran `uv sync --extra dev --extra analyzer --extra service --extra cli --extra nl --extra dense` to bring the venv back in line with `pyproject.toml`/`uv.lock` (both already declared `SPARQLWrapper>=2.0.0` since 04-01 — this was a venv-sync, not a new dependency addition). No `pyproject.toml` or `uv.lock` diff resulted.

## Known Stubs

None. Both files are integration test suites with no UI/data-rendering surface.

## Threat Flags

None beyond what the plan's own `<threat_model>` already anticipated: the background uvicorn server binds only `127.0.0.1` on an ephemeral port and tears down via `should_exit` + `thread.join` (T-04-09); `cosmic_coffee.rdf` is the same vendored, pinned-SHA static fixture from 04-01 parsed through the OwlBomb-capped, DOCTYPE/ENTITY-guarded import path from 04-02 (T-04-10); `SPARQLWrapper` was already legitimacy-audited in 04-RESEARCH.md (T-04-SC).

## Issues Encountered

None beyond the venv-sync noted above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- REQ-thirdparty-tool-compat's automated half (D-06) is fully proven Docker-gated; the documented-manual half (Protégé/YASGUI recipes, D-07) is a separate `docs/howto/` deliverable tracked elsewhere in the phase.
- No blockers for the next wave (04-06, performance SLOs).

---
*Phase: 04-interoperability-performance-verification*
*Completed: 2026-07-28*

## Self-Check: PASSED

- FOUND: tests/integration/test_sparqlwrapper_smoke.py
- FOUND: tests/integration/test_ontology_playground_roundtrip.py
- FOUND commit a19bea9 (Task 1)
- FOUND commit 2ed09f3 (Task 2)
- FOUND commit 1913648 (plan metadata / this summary)
- Re-verified this session (docker-gated): both files skip cleanly (`5 skipped`) without `RUN_INTEGRATION`; `RUN_INTEGRATION=1 uv run pytest tests/integration/test_sparqlwrapper_smoke.py tests/integration/test_ontology_playground_roundtrip.py -m integration -q` is green (`5 passed`) against a live docker-compose ArangoDB.
- Non-regression suite re-confirmed green this session: `uv run pytest -m "not integration and not w3c and not eval and not perf" -q` → 1428 passed, 0 failed (matches the count recorded above).
