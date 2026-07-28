# Phase 4: Interoperability & performance verification - Context

**Gathered:** 2026-07-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 builds the **verification harnesses** that prove `arango-sparql-py`'s
interoperability and performance claims. As originally scoped it covered four
requirements; this discussion **narrows the scope**:

- **REQ-foxx-parity** — **DESCOPED** this phase (see D-01). Legacy Foxx is
  deprecated; parity against it is retired as a v1.0 gate.
- **REQ-thirdparty-tool-compat** — third-party SPARQL tool smoke tests, split
  automated vs documented-manual (D-05..D-07).
- **REQ-ontoextract-integration** — the AOE roundtrip, reframed as testing
  **our own** `/mapping` import/export OWL fidelity + `/sparql` (D-03, D-04).
- **REQ-performance-slos** — the §9.4 budgets under a **tiered** enforcement
  posture: gate the cheap in-process rows, report the rest (D-08, D-09).

The phase delivers: a Foxx-deprecation ADR + roadmap/requirements amendment;
automated `/mapping` OWL-roundtrip and SPARQLWrapper/Playground smoke tests
(Docker-gated); documented how-to recipes with recorded transcripts for the
JVM/browser tools; and a tiered perf suite (CI-gated cheap rows +
local-run `LATENCY_REPORT.md` for the rest).

**Non-regression invariants (hard, carried across the whole project):** W3C
DAWG query-eval coverage ≥ 96.4%; the deterministic SPARQL→AQL transpiler
package untouched; scripted/no-network stays the CI default; no secrets
committed.

</domain>

<decisions>
## Implementation Decisions

### Foxx parity (REQ-foxx-parity)
- **D-01: Descope REQ-foxx-parity via an ADR waiver.** Legacy Foxx
  `arango-sparql` (the JS service this project rewrote) is **deprecated**.
  Validating parity against a dying reference has little value now that the
  W3C DAWG suite (96.4%) independently proves SPARQL→AQL correctness. Author
  an ADR (under `docs/architecture/`, PRD Appendix B) recording the
  deprecation and the decision to retire parity as a v1.0 acceptance gate.
- **D-02: Amend the plan of record.** Strike roadmap Phase 4 Success
  Criterion 1 (the "≥ 90% translatable legacy Foxx fixtures" golden), mark
  REQ-foxx-parity retired in `.planning/REQUIREMENTS.md` (v1.0 acceptance no
  longer depends on it), and note the retirement in PRD §3.7 / §13.4 (those
  sections describe a harness that will not be built). **No Foxx harness,
  no vendored Foxx fixtures, no `tests/legacy_roundtrip/`.**

### AOE ontoextract roundtrip (REQ-ontoextract-integration)
- **D-03: Test our half of the contract only — no live AOE.** AOE's own
  integration is "one env var" (§12.2); the substance worth testing is
  **our** endpoints. Do **not** clone/run the external `arango-ontoextract`
  service. Assert the real contract AOE depends on:
  `POST /mapping/export-owl` → `POST /mapping/import-owl` **triple-bag
  equality** (modulo blank-node renaming) plus `ASK`/`SELECT` via `/sparql`,
  running against our docker-compose ArangoDB.
- **D-04: Cover the OWL formats named in §12.2** — the import path handles
  Turtle / RDF-XML / JSON-LD / N-Triples; export covers Turtle + RDF/XML
  (§11.3). The roundtrip should exercise the formats AOE actually uses
  (Turtle + RDF/XML at minimum). A source OWL fixture is the planner's
  choice (a mapping fixture or a small curated ontology) — it must not
  require the AOE repo.

### Third-party tool compatibility (REQ-thirdparty-tool-compat)
- **D-05: Auto light, doc heavy.** Automate the cheap, high-value tools;
  document + hand-verify the JVM/browser-heavy ones. This matches §13.1's
  nightly/on-demand posture for interop tests.
- **D-06: Automated smoke tests** — SPARQLWrapper (pure Python, in-process
  against the running service) and the MS Ontology Playground roundtrip
  (file-based → exercises our `/mapping` routes; no external app). Both
  Docker-gated on a live ArangoDB. These are the `tests/integration/
  test_sparqlwrapper_smoke.py` and `test_ontology_playground_roundtrip.py`
  files the PRD already names.
- **D-07: Documented-manual** — Protégé (JVM desktop, driven headless via
  Apache Jena `arq`) and YASGUI (browser widget) get `docs/howto/` recipes
  (§11.4) with a **recorded smoke transcript** (SELECT + ASK + Service
  Description fetch) rather than an automated CI test. **No JVM/browser
  image in CI.**

### Performance SLOs (REQ-performance-slos)
- **D-08: Tiered enforcement.** CI-block **only** the fast, deterministic,
  in-process rows — `/translate` cold, `/translate` warm, `/execute`
  overhead (AQL pinned to `RETURN 1`) — with the §9.4 > 25%-regression
  tolerance kept generous to survive shared-runner jitter.
- **D-09: Report-not-gate the rest.** The Docker/LLM/noisy rows —
  `/sparql` GET, `/nl-translate` (live LLM, needs a key never placed in
  CI), `/schema/introspect`, memory-idle/load, concurrency, first-byte —
  run as a **local/on-demand** suite producing a checked-in
  `LATENCY_REPORT.md` artifact, reviewed by humans. §9.4's "CI fails on
  > 25%" becomes advisory for these rows. Baseline-sourcing methodology
  (how stable p95 numbers are captured/checked in) is the researcher's to
  design within this posture.

### Claude's Discretion
- Perf baseline capture/storage mechanics, the exact OWL roundtrip fixture,
  test file layout, and `arq`/how-to recipe wording are left to
  research/planning within the decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec & plan-of-record (amend per D-01/D-02)
- `.planning/ROADMAP.md` — Phase 4 block (Goal + 4 Success Criteria). **SC1
  is being struck** (D-02).
- `.planning/REQUIREMENTS.md` — REQ-foxx-parity (retire), REQ-thirdparty-tool-compat,
  REQ-ontoextract-integration, REQ-performance-slos + their acceptance rows.
- `docs/architecture/PRD.md` — the single source of truth. Relevant sections:
  - §3.7 (Foxx parity — being waived), §3.10 (tool compat), §3.11 (AOE), §3.12 (perf SLOs)
  - §9.4 Performance budgets (the 11-row SLO table)
  - §11.1 Compatibility matrix, §11.2–11.4 tool notes + `docs/howto/` recipe template
  - §12.2 `arango-ontoextract` integration commitments (the "one env var" contract)
  - §13.1 Test categories (markers: `legacy_roundtrip`, `perf`, `bench`, `integration`; nightly/on-demand gating)
  - §13.4 Legacy Foxx round-trip regression (describes the harness now being retired)

### Testing conventions & infra
- `.cursor/rules/200-testing.mdc` — testing rules + W3C harness conventions.
- `tests/integration/conftest.py` — Docker boot helpers (`docker compose up -d
  arangodb`, best-effort skip when Docker absent); ArangoDB defaults **host
  port 8532**, DB `sparql-to-aql` (never `_system`).
- `docker-compose.yml` — ArangoDB 3.12 service, host 8532 → container 8529.
- `CLAUDE.md` — hard rules (rdflib parser, AQL builder, pyoxigraph ground truth).

### ADR to author (D-01)
- `docs/architecture/` (PRD Appendix B is the ADR home) — new ADR: "Legacy
  Foxx parity retired (Foxx deprecated)".

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/integration/conftest.py`: plain-function Docker boot helpers
  (`ensure_test_database`, compose-up logic) already reused by the W3C-live
  harness — the perf, AOE-roundtrip, and tool-smoke suites reuse the same
  boot policy (port 8532, `sparql-to-aql` DB, best-effort skip).
- `tests/cross/`: existing pyoxigraph cross-validation pattern — the AOE
  triple-bag comparison can reuse pyoxigraph for graph parsing/equality.
- `/mapping/export-owl` + `/mapping/import-owl` routes already ship (Phase 2,
  9-route schema surface) — the AOE roundtrip wires existing endpoints, not
  new ones.

### Established Patterns
- **Scripted/no-network is the CI default; credentialed + Docker-heavy work is
  human-run and skip-gated.** Dominant across every NL phase (e.g.
  `NL2SPARQL_API_KEY` is human-held, never in CI). The perf `/nl-translate`
  row and any live sweeps follow this pattern.
- Docker-gated integration tests `pytest.skip(...)` cleanly when Docker is
  unavailable rather than failing.

### Integration Points
- AOE roundtrip + tool smoke tests run the FastAPI service against the
  docker-compose ArangoDB (host 8532).
- Perf CI-gated rows run in-process (no Docker) so they fit the per-PR path.

</code_context>

<specifics>
## Specific Ideas

- User's steer, verbatim: **"Foxx is deprecated."** This is the load-bearing
  reason REQ-foxx-parity is retired rather than harnessed.
- AOE reframed explicitly: the requirement is *named* after AOE but the
  testable substance is our own `/mapping` import/export OWL fidelity — do
  not stand up the external service.
- Ontology Playground is file-based (RDF/XML import/export), i.e. it exercises
  our `/mapping` routes — "testing Playground" needs no browser/app.

</specifics>

<deferred>
## Deferred Ideas

- **Live Foxx roundtrip** (PRD §13.4 as written) — rejected, not deferred:
  Foxx is deprecated, so the two-service Docker roundtrip is retired outright.
- **Full two-service AOE Docker roundtrip** (clone + run `arango-ontoextract`,
  drive the real Q7 flow) — deferred; revisit only if a real AOE
  integration regression surfaces that our own-half contract test can't catch.
- **Automated Protégé (JVM/`arq`) + YASGUI (browser) smoke in CI** — deferred;
  documented-manual + recorded transcript for now. Promote to automated only
  if tool-drift regressions warrant the CI image cost.
- **Full per-PR CI gating of all 11 §9.4 perf rows** — deferred; the noisy /
  LLM / Docker rows stay report-only until a stable dedicated perf runner
  exists.

</deferred>

---

*Phase: 4-interoperability-performance-verification*
*Context gathered: 2026-07-27*
