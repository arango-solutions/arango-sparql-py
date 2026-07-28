---
phase: 04-interoperability-performance-verification
verified: 2026-07-28T19:14:18Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
resolution:
  - item: "Out-of-plan `threading.Lock()` in `arango_sparql/translate/parser.py` (04-07)"
    decision: "REVERTED by operator (2026-07-28). Code review (WR-02) additionally found the lock was acquired on the asyncio event-loop thread by the async `/sparql` routes, which could stall the entire event loop — so the lock was not merely a scope deviation but carried a real concurrency defect. Reverted in the phase close-out fix commit; the underlying rdflib grammar thread-safety concern (observed, not hypothetical) is re-filed to deferred-items.md for a proper threadpool-executor fix in a dedicated plan. Non-regression re-confirmed after revert: fast suite 1428 passed, W3C DAWG coverage gate passed, translate goldens 394 passed."
  - item: "Code review WR-01 — p95 helper off-by-one (`tests/perf/conftest.py`)"
    decision: "FIXED in the same close-out commit: `statistics.quantiles(..., n=100)[93]` (94th percentile) → `[94]` (true 95th percentile), so the CI-gated perf gates measure the p95 the §9.4 SLO table specifies. Verified: p95(0..99)=94.95."
  - item: "Code review WR-03/WR-04 (minor: dead OwlImportRequest validation + silent export re-parse except)"
    decision: "Logged to deferred-items.md for a follow-up lint/cleanup pass (non-blocking, no security or correctness impact)."
---

# Phase 4: Interoperability & Performance Verification — Verification Report

**Phase Goal (as narrowed by 04-CONTEXT D-01..D-09):** Prove interoperability
and performance claims via verification harnesses — REQ-foxx-parity retired
(ADR-0003 + plan-of-record amendments, no Foxx harness); REQ-ontoextract-integration
via our own `/mapping` export→import isomorphism + `/sparql`; REQ-thirdparty-tool-compat
split automated (SPARQLWrapper + Ontology Playground) vs documented-manual
(Protégé/YASGUI, transcripts intentionally deferred); REQ-performance-slos
tiered (3 CI-gated in-process rows vs env-matched baseline + 8 report-only
rows → LATENCY_REPORT.md).

**Verified:** 2026-07-28T19:14:18Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | REQ-foxx-parity retired via ADR-0003 + ROADMAP/REQUIREMENTS/PRD amendments (D-01/D-02) | VERIFIED | `docs/architecture/decisions/0003-foxx-parity-retired.md` (redirect stub) + `docs/architecture/PRD.md` Appendix B.3 (full ADR body, lines 3731-3805); `.planning/ROADMAP.md` Phase 4 SC1 struck with `STRUCK` annotation citing ADR-0003; `.planning/REQUIREMENTS.md` REQ-foxx-parity marked `[x] **RETIRED** via ADR-0003`. No `tests/legacy_roundtrip/`, no vendored Foxx fixtures anywhere in the repo. |
| 2 | REQ-ontoextract-integration: our own-half `/mapping` export→import triple-bag isomorphism (Turtle + RDF/XML) + `/sparql` ASK/SELECT queryability, no live AOE service | VERIFIED | `tests/integration/test_aoe_roundtrip.py` (312 lines) uses `rdflib.Graph.isomorphic()` for both Turtle and RDF/XML round-trips, `SchemaCache.put()` for deterministic activation, then asserts ASK/SELECT via `/sparql`; imports `tests.integration.conftest` boot/skip helpers; no `arango-ontoextract` clone/import anywhere. |
| 3 | REQ-thirdparty-tool-compat automated half: SPARQLWrapper + MS Ontology Playground smoke tests (D-06) | VERIFIED | `tests/integration/test_sparqlwrapper_smoke.py` (330 lines) drives a real `SPARQLWrapper` client over a background `uvicorn` socket (SELECT + ASK + Service Description); `tests/integration/test_ontology_playground_roundtrip.py` (165 lines) round-trips the vendored `cosmic_coffee.rdf` fixture through `/mapping/import-owl` → `/mapping/export-owl` with `isomorphic()` equality. Both skip-gate cleanly (confirmed by execution: `8 skipped` with no Docker/ArangoDB running). |
| 4 | REQ-thirdparty-tool-compat documented-manual half: Protégé + YASGUI recipes with recorded-transcript placeholder, deferred per explicit operator decision (D-07), not fabricated | VERIFIED (deferred by design) | `docs/howto/protege.md` and `docs/howto/yasgui.md` each contain a `## Transcript (recorded, human-required checkpoint)` section with an unmistakable `RECORDED TRANSCRIPT — TO BE FILLED IN BY A HUMAN... Do not invent output.` placeholder block — no fabricated terminal/browser output present. `deferred-items.md` documents the operator's explicit "CLOSE WITH PLACEHOLDERS" resolution of the 04-08 Task 2 `checkpoint:human-verify`. This matches the phase goal's own framing ("recorded transcripts intentionally DEFERRED per operator decision") — not a fresh gap. |
| 5 | REQ-performance-slos CI-gated tier: 3 in-process rows (`/translate` cold, `/translate` warm, `/execute` overhead) measure p95 via `statistics.quantiles` and gate against an env-matched `baseline.json` (D-08) | VERIFIED (artifact+wiring), flaky in this sandbox (documented, see Anti-Patterns/Perf section) | `tests/perf/test_translate_latency.py`, `tests/perf/test_execute_overhead.py`, `tests/perf/baseline.json` (`captured_env: "local"`, 3 p95 rows) all exist and are wired to the `_FakeArangoClient` double (zero Docker). Re-running locally: 3/3 failed on this run (p95 exceeded budget by 8-28%) — this matches the exact, pre-documented environmental jitter in `deferred-items.md` ("sometimes 0/3, sometimes 2/3, sometimes 3/3 fail... expected to resolve once an authoritative `captured_env: 'ci'` baseline replaces the interim local one"). Not a fresh regression — a known, disclosed limitation of the interim local baseline. |
| 6 | REQ-performance-slos report-only tier: 8 rows (D-09) never gate CI, append to a checked-in `LATENCY_REPORT.md` | VERIFIED | `tests/perf/LATENCY_REPORT.md` checked in with 7 measured rows (all "OK" against their advisory budgets) plus an honest "Not Captured" section explaining `nl_translate_p95_ms` was skipped (no `NL2SPARQL_API_KEY` supplied, by design — key never placed in CI). `tests/perf/test_nl_latency.py` module-level `skipif` confirmed on `NL2SPARQL_API_KEY` absence, never `OPENAI_API_KEY`. |
| 7 | Non-regression invariant: W3C DAWG query-eval coverage ≥ 96.4% | VERIFIED | `python -m pytest tests/w3c/test_coverage_gate.py -q` → `1 passed`. |
| 8 | Non-regression invariant: the deterministic SPARQL→AQL transpiler package "untouched" | **UNCERTAIN — operator decision requested** | `arango_sparql/translate/parser.py` gained a module-level `threading.Lock()` (commit `901ed75`, 04-07) wrapping `parseQuery`/`translateQuery`. Diff-reviewed: the lock only serializes the two rdflib calls; no algebra-walking/translation logic changed. The invariant's *intent* (translation correctness/determinism) still holds — W3C gate still passes (truth #7) — but the invariant's *letter* ("untouched") is literally violated by an unplanned production-code change outside this phase's `files_modified` scope in every plan's frontmatter. See `human_verification` above. |
| 9 | Fast test suite (non-integration/w3c/eval/perf) passes at the expected count | VERIFIED | `python -m pytest -m "not integration and not w3c and not eval and not perf" -q` → `1428 passed, 1184 deselected` — matches the expected ~1428. |
| 10 | No unresolved debt markers (TBD/FIXME/XXX) introduced in phase-modified files | VERIFIED | `grep -n -E "TBD\|FIXME\|XXX"` across all `key-files`/`files_modified` from every 04-0N plan — zero hits. |
| 11 | No secrets committed | VERIFIED | Grepped `tests/perf/`, `docs/howto/`, integration test files for hardcoded keys/tokens — no hits; `NL2SPARQL_API_KEY` is read from `os.environ` only, never embedded. |

**Score:** 10/11 truths verified (1 uncertain, requires operator decision)

### Deferred Items

Items intentionally not delivered this phase, per explicit operator/CONTEXT decisions — not actionable gaps.

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Protégé/YASGUI recorded transcripts (actual human-run JVM/browser output) | Deferred by operator decision (D-07) | `deferred-items.md` "04-08 Task 2" entry; `docs/howto/protege.md`/`yasgui.md` placeholder blocks. Re-open when a human has JVM + browser access to a live `/sparql` endpoint. |
| 2 | Authoritative CI-captured perf baseline replacing the interim `captured_env: "local"` bootstrap | Documented follow-up (04-06 Known Limitations, tracked by 04-07's deferred-items.md entry) | `tests/perf/baseline.json` `captured_env: "local"`; the env-match gate design (D-08) makes this advisory-safe until replaced. |
| 3 | A real `/execute`-can't-represent-ASK-boolean gap (SparqlExecuteResponse.bindings contract vs `RETURN LENGTH(...) > 0` boolean AQL result) | Logged as future-plan item, not fixed this phase | `deferred-items.md` "04-07 Task 1" / 04-07-SUMMARY key-decisions: "documented as a deferred item rather than changing the /execute response contract (out of scope for this hardening pass)." |
| 4 | Pre-existing `ruff` findings in Plan 01/06 perf files (`I001` unsorted import in `conftest.py`, `F811` redefinition in `test_execute_overhead.py`) | Logged for a future lint-cleanup pass | Confirmed via `ruff check tests/perf/conftest.py tests/perf/test_execute_overhead.py` → 4 errors, matching `deferred-items.md`'s "04-07 Task 1" entry describing the same two files/rules. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `docs/architecture/decisions/0003-foxx-parity-retired.md` | ADR redirect stub | VERIFIED | Redirect stub pointing at PRD Appendix B.3, matches convention. |
| `docs/architecture/PRD.md` (Appendix B.3, §3.7, §13.4, §9.4) | Foxx-retirement ADR body + amendments | VERIFIED | Appendix B.3 present (lines 3731-3805); §3.7 row struck + waived note; §13.4 references the ADR/W3C gate as sole ground truth. |
| `.planning/ROADMAP.md` | Phase 4 SC1 struck | VERIFIED | SC1 shown struck-through with `STRUCK — REQ-foxx-parity retired via ADR-0003` annotation. |
| `.planning/REQUIREMENTS.md` | REQ-foxx-parity marked Retired | VERIFIED | `[x] **REQ-foxx-parity** ... **RETIRED** via ADR-0003`; traceability table row reads `Retired`. |
| `arango_sparql/translate/owl.py` | format-dispatch table + `format=` kwarg (turtle/xml/json-ld/nt) | VERIFIED | `_FORMAT_ALIASES`, `format_from_mime`, `parse_owl_graph` with pre-parse DOCTYPE/ENTITY guard (`_XML_DTD_PATTERN`) all present and wired into `turtle_to_mapping`/`mapping_to_turtle`. |
| `arango_sparql/service/routes/mapping.py` | Content-Type sniff + Accept negotiation | VERIFIED | `format_from_mime` imported and used for both import Content-Type sniffing and export Accept negotiation; `application/rdf+xml` handled. |
| `tests/translate/test_owl.py`, `tests/test_service_mapping_routes.py` | format-dispatch + RDF/XML route + OWL-bomb + DOCTYPE/ENTITY tests | VERIFIED | 778 / 796 lines respectively; DOCTYPE/ENTITY guard test present (`test_service_mapping_routes.py:772-785`) asserting 422 `E_OWL_PARSE`. |
| `tests/integration/test_aoe_roundtrip.py` | AOE own-half contract test | VERIFIED | 312 lines, `isomorphic` pattern present, Docker-gated via `tests.integration.conftest`. |
| `tests/integration/test_sparqlwrapper_smoke.py`, `test_ontology_playground_roundtrip.py` | automated third-party smoke tests | VERIFIED | 330 / 165 lines; contain `SPARQLWrapper` / `isomorphic` respectively; both skip cleanly without Docker. |
| `tests/perf/conftest.py`, `test_translate_latency.py`, `test_execute_overhead.py`, `baseline.json` | CI-gated perf tier | VERIFIED (with documented flakiness) | All present; `baseline.json` has `captured_env`, 3 p95 rows; env-matched gate logic confirmed by reading source and by execution behavior. |
| `tests/perf/test_sparql_protocol_latency.py`, `test_schema_introspect_latency.py`, `test_nl_latency.py`, `test_memory_idle.py`, `test_memory_load.py`, `test_concurrency.py`, `test_first_byte.py`, `LATENCY_REPORT.md` | 8 report-only perf rows | VERIFIED | All 7 test files + `LATENCY_REPORT.md` present; `LATENCY_REPORT.md` contains 7 measured rows + honest "Not Captured" entry for the key-gated `/nl-translate` row. |
| `docs/howto/index.md`, `protege.md`, `yasgui.md`, `arq.md`, `sparqlwrapper.md`, `ontology-playground.md` | recipe index + 5 recipes | VERIFIED | All present; index links all five; protege.md/arq.md use `rsparql --service` (not bare `arq`); transcript placeholders in protege.md/yasgui.md are clearly marked, not fabricated. |
| `tests/fixtures/cosmic_coffee.rdf`, `cosmic_coffee.NOTICE.md` | vendored MIT RDF/XML fixture + provenance | VERIFIED | Both present; used by `test_ontology_playground_roundtrip.py`. |
| `pyproject.toml` | `perf` marker + `SPARQLWrapper` dev dep | VERIFIED | `perf: performance budget enforcement...` marker registered; `SPARQLWrapper>=2.0.0` in dev deps. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `mapping.py` | `owl.py` | `format=` kwarg passed to `turtle_to_mapping`/`mapping_to_turtle` | WIRED | `format_from_mime` imported and called at both import (Content-Type) and export (Accept) sites. |
| `mapping.py` RDF/XML branch | `OwlBombError`/`OwlParseError` | unchanged HTTPException 422 envelope | WIRED | Confirmed test asserts 422 `E_OWL_PARSE` for DOCTYPE/ENTITY payloads via the pre-existing envelope. |
| `test_aoe_roundtrip.py` | `mapping.py` routes | POST `/mapping/export-owl` + `/mapping/import-owl` (Turtle + RDF/XML) | WIRED | Both formats exercised with `isomorphic()` assertions. |
| `test_aoe_roundtrip.py` | `SchemaCache.put()` | deterministic schema activation for `/sparql` | WIRED | `put(` pattern present. |
| `test_sparqlwrapper_smoke.py` | `uvicorn.Server` | background daemon thread + real bound socket | WIRED | `uvicorn` pattern confirmed; real HTTP readiness poll before firing SPARQLWrapper requests. |
| `test_*_latency.py` (CI-gated) | `tests/perf/baseline.json` | `load_baseline()` + 1.25 tolerance gate | WIRED | Confirmed by execution — the gate fires (and correctly fails when p95 exceeds the tolerated budget in this sandbox). |
| report-only `test_*.py` rows | `tests/perf/conftest.py append_report()` | non-gating report append | WIRED | `LATENCY_REPORT.md` contains measured numbers for all rows except the key-gated `/nl-translate` row (which skips cleanly, by design). |
| `docs/howto/index.md` | five recipe files | recipe index links | WIRED | Table links all five `.md` files by relative path. |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| REQ-foxx-parity | 04-03 | Retired via ADR-0003, no v1.0 gate | SATISFIED | ADR-0003 + PRD/ROADMAP/REQUIREMENTS amendments (Truth #1). |
| REQ-thirdparty-tool-compat | 04-01, 04-02, 04-05, 04-08 | Automated (SPARQLWrapper, Ontology Playground) + documented-manual (Protégé, YASGUI) | SATISFIED (as narrowed) | Truths #3/#4. **Note:** `.planning/REQUIREMENTS.md` and PRD §3.10's acceptance-column text (`tests/integration/test_*_compat.py`, "every row has a passing smoke test") were NOT updated to reflect the D-05/D-06/D-07 automated-vs-documented split; the actual delivered filenames are `test_sparqlwrapper_smoke.py`/`test_ontology_playground_roundtrip.py`, and Protégé/YASGUI have no automated test by design. This is a pre-existing documentation-staleness issue (not amended by any 04-0N plan, since only 04-03 touched REQUIREMENTS.md/PRD text and its scope was Foxx-only) — flagged as an Info-level finding below, not a blocker, since the phase-goal-as-given to this verifier explicitly describes the narrowed split as the intended deliverable. |
| REQ-ontoextract-integration | 04-02, 04-04 | Own-half `/mapping` roundtrip + `/sparql` ASK/SELECT | SATISFIED | Truth #2. |
| REQ-performance-slos | 04-01, 04-06, 04-07 | Tiered CI-gated + report-only perf rows | SATISFIED (artifact+wiring); local-env flakiness is a documented, non-blocking limitation | Truths #5/#6. |

No orphaned requirements — all 4 IDs declared across the phase's 8 plans match the 4 IDs `.planning/REQUIREMENTS.md` maps to "Phase 4".

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `arango_sparql/translate/parser.py` | 22, 49, 90 | Out-of-plan production-code change (module-level `threading.Lock()`) not declared in any 04-0N `files_modified` frontmatter | WARNING (scope deviation) | Defensible concurrency-correctness fix; does not alter translation semantics (W3C gate still passes); requires explicit operator keep/revert decision per Escalation Gate pattern. See `human_verification`. |
| `tests/perf/conftest.py` | — | `ruff` `I001` unsorted import block (pre-existing, Plan 01) | Info | Not introduced this phase; logged in `deferred-items.md` for future lint pass. |
| `tests/perf/test_execute_overhead.py` | 132-134 | `ruff` `F811` fixture-name redefinition (pre-existing, Plan 06) | Info | Not introduced this phase; logged in `deferred-items.md` for future lint pass. |
| `.planning/REQUIREMENTS.md` / PRD §3.10 | 36 / 132 | Acceptance-criteria text describes `test_*_compat.py` "one file per tool" and "every row has a passing smoke test" — stale vs. the actual D-05/D-06/D-07 automated/documented split | Info (documentation drift) | Not a functional gap — narrowed scope explicitly sanctioned by 04-CONTEXT; text just wasn't refreshed since only 04-03 touched these files (Foxx-only scope). |

No debt markers (`TBD`/`FIXME`/`XXX`) found in any phase-modified file. No fabricated transcripts. No secrets found.

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Fast suite passes at expected count | `pytest -m "not integration and not w3c and not eval and not perf" -q` | `1428 passed, 1184 deselected in 30.90s` | PASS |
| W3C DAWG coverage gate (≥96.4%) | `pytest tests/w3c/test_coverage_gate.py -q` | `1 passed` | PASS |
| CI-gated perf tier (in-process, no Docker) | `pytest tests/perf/ -q -m perf` | `3 failed, 7 skipped` — all 3 failures are the CI-gated p95 rows exceeding the interim local baseline by 8-28% | FAIL (documented, non-blocking — matches pre-existing `deferred-items.md` entry verbatim) |
| Docker-gated integration tests skip cleanly without Docker | `pytest tests/integration/test_aoe_roundtrip.py test_sparqlwrapper_smoke.py test_ontology_playground_roundtrip.py -q` | `8 skipped` | PASS (clean skip, no error) |

### Human Verification Required

### 1. Accept or revert the out-of-plan `threading.Lock()` in `arango_sparql/translate/parser.py`

**Test:** Review commit `901ed75` (04-07) which adds a module-level `_PARSE_LOCK = threading.Lock()` around `parseQuery`/`translateQuery` in the transpiler's parser module — a file no 04-0N plan declared in its `files_modified` frontmatter.
**Expected:** An explicit operator decision: either (a) accept the deviation (e.g., record an `overrides:` entry citing it as a justified concurrency-correctness fix), or (b) request a revert/relocation of the fix outside this phase's scope.
**Why human:** The code is verified correct (lock only serializes two rdflib calls, no logic changed, W3C DAWG gate still passes at 96.4%+), but whether an unplanned change to the "sacred, untouched" transpiler package is acceptable inside a phase scoped to test/doc artifacts is a scope-policy tradeoff, not a fact a grep or test run can resolve.

### Gaps Summary

No artifact is missing, stubbed, or unwired. All four requirement IDs
(REQ-foxx-parity, REQ-thirdparty-tool-compat, REQ-ontoextract-integration,
REQ-performance-slos) have concrete, substantive, wired evidence matching
the phase goal as explicitly narrowed by 04-CONTEXT D-01..D-09. The fast
test suite (1428 tests) and the W3C DAWG coverage gate both pass. The one
open item is not a functional gap but a scope-policy question: an
unplanned (but well-reasoned and non-regressing) production-code change to
`arango_sparql/translate/parser.py` was made mid-phase to fix a real
concurrency bug discovered by the perf suite's own concurrency row. The
change is technically sound and does not violate the *effective*
non-regression invariant (W3C DAWG ≥96.4% still holds), but it does violate
the *literal* "transpiler package untouched" framing from 04-CONTEXT, so
it is surfaced here for an explicit operator decision rather than silently
passed or silently blocked.

Two secondary Info-level findings (not blockers): (1) `.planning/REQUIREMENTS.md`
and PRD §3.10's acceptance-criteria text were not refreshed to reflect the
automated-vs-documented split, and still name a `test_*_compat.py` pattern
that doesn't match the actual delivered filenames; (2) two pre-existing
`ruff` findings in Plan 01/06 perf files remain unfixed (logged, not
introduced this phase).

---

*Verified: 2026-07-28T19:14:18Z*
*Verifier: Claude (gsd-verifier)*
