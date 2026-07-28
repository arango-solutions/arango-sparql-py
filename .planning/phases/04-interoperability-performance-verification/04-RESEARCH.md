# Phase 4: Interoperability & performance verification - Research

**Researched:** 2026-07-27
**Domain:** Verification-harness engineering — HTTP-protocol interop smoke tests, OWL round-trip fidelity, tiered performance-SLO benchmarking, ADR/documentation amendment
**Confidence:** MEDIUM-HIGH (every load-bearing claim below was verified by reading this repo's own code or by executing a tool directly this session; the few genuinely external facts — e.g. Ontology-Playground catalogue licensing — are cited to their source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Foxx parity (REQ-foxx-parity)**
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

**AOE ontoextract roundtrip (REQ-ontoextract-integration)**
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

**Third-party tool compatibility (REQ-thirdparty-tool-compat)**
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

**Performance SLOs (REQ-performance-slos)**
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

### Deferred Ideas (OUT OF SCOPE)
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

**Non-regression invariants (hard, carried across the whole project):** W3C
DAWG query-eval coverage ≥ 96.4%; the deterministic SPARQL→AQL transpiler
package untouched; scripted/no-network stays the CI default; no secrets
committed.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-foxx-parity | RETIRED this phase via ADR waiver (D-01/D-02) — no harness built | ADR-0003 drafting pattern (mirrors existing ADR-0001/0002 in PRD Appendix B); exact amendment locations identified in REQUIREMENTS.md, ROADMAP.md, PRD §3.7/§13.4 |
| REQ-thirdparty-tool-compat | SPARQLWrapper + Ontology Playground automated smoke (D-06); Protégé/YASGUI documented-manual (D-07) | SPARQLWrapper API verified (official docs + PyPI); live-uvicorn-in-thread pattern for in-process HTTP; vendored `cosmic-coffee.rdf` fixture verified (MIT, 349 triples); `rsparql` CLI verified installed+working via Homebrew `jena` formula |
| REQ-ontoextract-integration | Own-half contract test: export-owl → import-owl triple-bag equality + ASK/SELECT via `/sparql` (D-03/D-04) | `rdflib.Graph.isomorphic()` verified for blank-node-safe triple-bag equality; **critical gap found**: current `owl.py`/`mapping.py` hardcode `format="turtle"` — RDF/XML is NOT yet implemented despite being PRD-documented; `SchemaCache.put()` identified as the deterministic way to make an imported mapping queryable via `/sparql` without depending on heuristic auto-detection |
| REQ-performance-slos | Tiered CI-gate (3 fast rows) + report-only `LATENCY_REPORT.md` (D-08/D-09) | **Critical gap found**: `/execute` genuinely calls live ArangoDB (`session.db.aql.execute`), contradicting D-08's "in-process" framing unless the existing `_FakeArangoClient` test double (already in `tests/test_service_sparql_routes.py`) is reused to stub AQL dispatch; hand-rolled JSON-baseline approach recommended over `pytest-benchmark` (percentile gap identified); `perf` pytest marker does not yet exist in `pyproject.toml` |
</phase_requirements>

## Summary

This phase is almost entirely a **test/docs/ADR-authoring** phase, and the
codebase already has every low-level primitive it needs: a pyoxigraph-based
ground-truth pattern (`tests/cross/`, `tests/helpers/oxi.py`), a Docker-gated
integration-test convention (`tests/integration/conftest.py`,
`docker-compose.yml`, host port 8532 / DB `sparql-to-aql`), a `_FakeArangoClient`
test double that already exercises the full `/execute` dispatch path without a
real database (`tests/test_service_sparql_routes.py`), and a `SchemaCache.put()`
write path (`arango_sparql/schema/cache.py:207`) that lets a test inject an
OWL-derived mapping directly, bypassing analyzer/heuristic auto-detection.
Research this session surfaced **two genuine gaps that change what "verification
harness, not new features" means in practice** for this phase:

1. **RDF/XML import/export is not implemented.** `turtle_to_mapping()` and
   `mapping_to_turtle()` (`arango_sparql/translate/owl.py`) and the
   `/mapping/import-owl` / `/mapping/export-owl` routes
   (`arango_sparql/service/routes/mapping.py`) hardcode
   `format="turtle"` end-to-end — there is no Content-Type/Accept dispatch to
   any other rdflib format. D-04 locks in "cover Turtle + RDF/XML at minimum"
   for the AOE own-half contract test, and PRD §11.3's Ontology Playground
   roundtrip is *specifically* an RDF/XML fixture. Closing this gap requires
   a small, mechanical addition (an rdflib format-name lookup table — `xml`,
   `turtle`, `json-ld`, `nt` are all built into installed rdflib 7.6 with zero
   extra dependencies, verified directly this session) rather than new
   product surface, but it is still a **production code change**, not test-only
   — the planner must budget a task for it and should not assume "just write
   the test" suffices for the RDF/XML row.
2. **`/execute` is not actually in-process.** `session.db.aql.execute(...)`
   is a real ArangoDB round-trip (`arango_sparql/service/routes/sparql.py:265`).
   D-08 calls the `/execute overhead` row "in-process," but as written today
   it needs a live database. The existing `_FakeArangoClient` /
   `_FakeCursor` test double already used by
   `tests/test_service_sparql_routes.py` resolves this cleanly: it drives the
   real `TestClient(app)` through `/connect` → `/translate` → `/execute`
   with a monkeypatched `ArangoClient`, so the CI-gated perf rows can
   measure genuine translate+dispatch overhead with **zero Docker
   dependency**, exactly matching §9.4's own "excluding AQL exec" carve-out
   for that row.

**Primary recommendation:** Reuse existing test infrastructure aggressively
(the `_FakeArangoClient` double for perf, the `tests/integration/conftest.py`
Docker-boot helpers for the two Docker-gated smoke tests, `rdflib.compare`
for triple-bag equality) rather than building new scaffolding; budget one
small, explicitly-scoped production-code task (RDF/XML format plumbing) up
front so the AOE and Ontology-Playground tests aren't blocked on missing
functionality; and adopt a hand-rolled JSON-baseline perf harness (mirroring
the already-proven `tests/nl2sparql/eval/baseline.json` convention) rather
than introducing `pytest-benchmark`, because the PRD's SLO table is keyed on
**p95**, which `pytest-benchmark` does not report natively.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| RDF/XML + JSON-LD + N-Triples format plumbing for OWL import/export | API / Backend (`arango_sparql/translate/owl.py`, `service/routes/mapping.py`) | — | Pure server-side rdflib format dispatch; no client involvement |
| AOE own-half triple-bag + ASK/SELECT contract test | API / Backend (test exercises `/mapping/*` + `/sparql`) | Database / Storage (docker-compose ArangoDB backs the `/sparql` query) | The "contract" is entirely HTTP-surface + AQL dispatch; AOE itself is out of scope (D-03) |
| SPARQLWrapper smoke test | API / Backend (our `/sparql` route is the target) | — | Client is a pure-Python library making real HTTP calls to our own service (see Pitfall 2 — needs a bound live server, not a `TestClient`) |
| Ontology Playground roundtrip | API / Backend (`/mapping/export-owl` ↔ `/mapping/import-owl`) | — | File-based; no browser, no live SPARQL (§11.3) |
| Protégé / YASGUI documented-manual recipes | External Client Tool (JVM desktop / browser widget, out-of-repo) | API / Backend (our `/sparql` endpoint is what they connect to) | Neither tool runs in CI; the recipe + transcript document real behaviour against our HTTP surface |
| Tiered perf suite (CI-gated 3 rows) | API / Backend (`/translate`, `/execute` dispatch path) | — | Measured via `TestClient(app)` + `_FakeArangoClient`, no real DB |
| Tiered perf suite (report-only 8 rows) | API / Backend + Database / Storage | — | `/sparql` GET, `/schema/introspect`, memory/concurrency rows need the real docker-compose ArangoDB; `/nl-translate` needs a live LLM |
| ADR + doc amendments (Foxx retirement) | Documentation (not a runtime tier) | — | `docs/architecture/PRD.md` Appendix B + `.planning/` amendments; no code |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `rdflib` | 7.6.0 installed; pyproject pins `>=7.0` | OWL parse/serialize (Turtle, RDF/XML, JSON-LD, N-Triples all built in), `rdflib.compare` graph isomorphism | Already the project's mandated parser (CLAUDE.md hard rule #1); no new dependency needed — the RDF/XML gap is a *usage* gap, not a *library* gap `[VERIFIED: executed directly this session against the installed venv]` |
| `pyoxigraph` | 0.5.9 installed; pyproject pins `>=0.3.22` | Already the project's W3C ground-truth store; optionally usable as a secondary sanity check on the RDF/XML fixture (confirmed `RdfFormat.RDF_XML` and `JSON_LD` exist) | Already a `[dev]` dependency; no new install `[VERIFIED: executed directly this session]` |
| `SPARQLWrapper` | 2.0.0 current on PyPI | The exact client PRD §11.1 names for the automated smoke test | Canonical RDFLib-org Python SPARQL client; `slopcheck` OK, no `NO_REPO`/suspicious flags `[VERIFIED: PyPI registry `pip index versions`; docs fetched from sparqlwrapper.readthedocs.io]` |
| `uvicorn` | 0.35.0 installed; pyproject pins `>=0.20.0` | Needed to bind a *real* live HTTP server in a background thread so `SPARQLWrapper` (a real `urllib`-based HTTP client) has something to connect to — a `fastapi.testclient.TestClient` does not expose a real socket `SPARQLWrapper` can target | Already a core dependency; `uvicorn.Config`/`Server` supports the standard "run in a daemon thread, `should_exit` to stop" pattern `[VERIFIED: Config signature introspected against the installed 0.35.0 package]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Apache Jena (`rsparql` CLI, part of the `jena` formula) | 6.1.0 (Homebrew bottle, verified installed+working this session) | Headless-driven SPARQL client for the Protégé documented-manual recipe (D-07) | `docs/howto/protege.md` + `docs/howto/arq.md` transcript capture only — never in CI |
| `statistics` (stdlib) | Python 3.11+ builtin | `statistics.quantiles(data, n=100)` for p95/p99 computation in the hand-rolled perf harness | Perf baseline capture (see Validation Architecture) — no new dependency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled perf timing + JSON baseline | `pytest-benchmark` 5.2.3 | `pytest-benchmark` gives built-in warmup/calibration/outlier detection and a native `--benchmark-compare-fail=mean:25%` CI gate, but its **native stats are min/max/mean/stddev/median/iqr — no p95/p99** (confirmed via its own docs); the PRD's SLO table is keyed on p95. Raw per-round data is available via `--benchmark-json` so p95 *could* be computed downstream, but at that point you're writing the same custom percentile script either way, plus a new dependency and a `.benchmarks/` storage convention that diverges from this repo's existing `baseline.json`-in-`tests/` convention (Phase 6 eval harness). **Recommendation: hand-rolled**, matching the proven convention. |
| `SchemaCache.put()` direct injection (deterministic) | Seed real ArangoDB collections and let heuristic/analyzer auto-detection discover the schema (mirrors `_seeded_collection` in `tests/integration/test_execute_endpoint.py`) | Auto-detection is closer to "real" AOE usage, but non-deterministic w.r.t. which style (heuristic vs analyzer) wins, and the analyzer extra needs an LLM-backed classifier for non-trivial mappings. Direct cache injection deterministically tests exactly the OWL→bundle→AQL path the AOE contract cares about. **Recommendation: `SchemaCache.put()` for the AOE contract test**; the existing `_seeded_collection`-style pattern remains right for tests that want to prove auto-detection itself. |

**Installation:**
```bash
# SPARQLWrapper: add to the [dev] extra (or a new [interop] extra) in pyproject.toml
pip install "SPARQLWrapper==2.0.0"

# Apache Jena (arq/rsparql) — developer machine only, NEVER in CI (D-07)
brew install jena   # macOS; verified this session — installs rsparql, arq, sparql, riot, etc.
```

**Version verification:** `pip index versions SPARQLWrapper` → `2.0.0` (latest); `rdflib`/`pyoxigraph`/`uvicorn` versions above were read directly from the installed venv this session (`python3 -c "import X; print(X.__version__)"`), not from training data.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `SPARQLWrapper` | PyPI | Long-lived RDFLib-org project (2.0.0 is a major-version-bump release; 1.x line dates back over a decade) | High (RDFLib ecosystem staple) | `github.com/RDFLib/sparqlwrapper` | `OK`, no flags | Approved |
| `pytest-benchmark` | PyPI | Mature (5.2.3, versions back to 0.1.0) | High | Not linked on PyPI metadata | `OK` with `NO_REPO` info flag ("no source repository linked") | Not recommended for adoption this phase (see Alternatives table) — not disposed as unsafe, simply unneeded |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** none.

Both packages were scanned via `slopcheck scan --pkg pypi <name> --json` this session (not the `install` subcommand, to avoid actually installing anything). `SPARQLWrapper`'s legitimacy is additionally corroborated by its official docs (sparqlwrapper.readthedocs.io) and GitHub org (RDFLib), so it is tagged `[CITED]` rather than merely `[ASSUMED]` above. `pytest-benchmark` is not being recommended for adoption, so its provenance is informational only.

Apache Jena is **not a pip/npm package** — it is a JVM tool distributed via Homebrew (`brew install jena`) or the official Apache tarball. It was installed and exercised directly this session (see Code Examples) rather than merely looked up, which is the strongest verification tier available for a non-registry tool.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌────────────────────────────────────────────┐
                    │        Phase 4 verification harnesses       │
                    └────────────────────────────────────────────┘

  (A) AOE own-half contract test (D-03) — Docker-gated (`integration` marker)
  ────────────────────────────────────────────────────────────────────────
  phys:-annotated Turtle fixture (extend the proven `_PERSON_ONTOLOGY_TTL`
  pattern from tests/integration/test_execute_endpoint.py)
        │
        ▼
  turtle_to_mapping()  ──►  MappingBundle  ──►  mapping_to_turtle()/[NEW: mapping_to_rdfxml()]
        │                                              │
        │  POST /mapping/import-owl                    │  POST /mapping/export-owl
        ▼                                              ▼
  arango_sparql/service/routes/mapping.py  ◄──────────────┘
        │
        │  rdflib.compare.to_isomorphic(g1) == to_isomorphic(g2)   (blank-node-safe
        ▼                                                            triple-bag equality)
  [ASSERT: round-trip fidelity, Turtle AND RDF/XML]
        │
        │  SchemaCache().put(db_name, bundle)   ← deterministic activation,
        ▼                                          bypasses heuristic/analyzer auto-detect
  POST /connect  →  session.db bound to docker-compose ArangoDB (port 8532, db `sparql-to-aql`)
        │
        ▼
  POST /sparql  { ASK {...} }, { SELECT ... }
        │
        ▼
  [ASSERT: 200 + well-formed SPARQL Results, matching the seeded/empty collection state]


  (B) SPARQLWrapper smoke test (D-06) — Docker-gated
  ────────────────────────────────────────────────────────────────────────
  uvicorn.Server(Config(app, host="127.0.0.1", port=<ephemeral>))
        │  .run() in a background daemon thread (real bound socket)
        ▼
  SPARQLWrapper("http://127.0.0.1:<port>/sparql")
        │  .setQuery(...) / .setReturnFormat(JSON) / .query().convert()
        ▼
  Real HTTP POST → our /sparql route → session (from a prior /connect) → docker-compose ArangoDB
        │
        ▼
  [ASSERT: SELECT bindings, ASK boolean, Service Description fetch all succeed]


  (C) Ontology Playground roundtrip (D-06) — Docker-gated (file-based only, no live SPARQL)
  ────────────────────────────────────────────────────────────────────────
  vendored catalogue/official/cosmic-coffee/cosmic-coffee.rdf (RDF/XML, MIT, 349 triples)
        │  POST /mapping/import-owl  (Content-Type: application/rdf+xml)  [NEEDS THE RDF/XML GAP FIX]
        ▼
  MappingBundle  ──►  POST /mapping/export-owl (Accept: application/rdf+xml)
        │
        ▼
  rdflib isomorphic comparison against the original cosmic-coffee.rdf graph


  (D) Tiered perf suite — CI-gated rows (D-08), zero Docker
  ────────────────────────────────────────────────────────────────────────
  TestClient(app) + monkeypatch ArangoClient → _FakeArangoClient/_FakeDb/_FakeCursor
  (proven pattern already living in tests/test_service_sparql_routes.py)
        │
        ▼
  N iterations of POST /translate (cold, then warm) and POST /execute (AQL pinned to
  "RETURN 1", fake cursor returns instantly) via time.perf_counter()
        │
        ▼
  statistics.quantiles(samples, n=100)[93]  → p95   (pure stdlib, no numpy/scipy)
        │
        ▼
  Compare against checked-in tests/perf/baseline.json; fail if p95 > baseline_p95 * 1.25


  (E) Tiered perf suite — report-only rows (D-09), Docker + optional live LLM
  ────────────────────────────────────────────────────────────────────────
  Real docker-compose ArangoDB (/sparql GET, /schema/introspect, memory, concurrency,
  first-byte) + optional NL2SPARQL_API_KEY (/nl-translate)
        │
        ▼
  tests/perf/LATENCY_REPORT.md  (checked in, human-reviewed, advisory only — never gates CI)
```

### Recommended Project Structure
```
tests/
├── integration/
│   ├── test_sparqlwrapper_smoke.py        # D-06, new — needs a live-uvicorn-thread fixture
│   ├── test_ontology_playground_roundtrip.py  # D-06, new — file-based, no live server needed
│   └── test_aoe_roundtrip.py               # D-03/D-04, new — Docker-gated, SchemaCache.put()
├── perf/                                   # NEW top-level dir — none exists today
│   ├── conftest.py                         # in-process TestClient + _FakeArangoClient reuse
│   ├── baseline.json                       # checked-in, mirrors tests/nl2sparql/eval/baseline.json convention
│   ├── test_translate_latency.py           # CI-gated (D-08)
│   ├── test_execute_overhead.py            # CI-gated (D-08)
│   ├── test_sparql_protocol_latency.py     # report-only (D-09)
│   ├── test_schema_introspect_latency.py   # report-only (D-09)
│   ├── test_nl_latency.py                  # report-only (D-09), RUN_EVAL-style gate for the live LLM key
│   ├── test_memory_idle.py                 # report-only (D-09)
│   ├── test_memory_load.py                 # report-only (D-09)
│   ├── test_concurrency.py                 # report-only (D-09)
│   ├── test_first_byte.py                  # report-only (D-09)
│   └── LATENCY_REPORT.md                   # checked-in artifact for the report-only rows
├── fixtures/
│   └── cosmic_coffee.rdf                   # vendored MS Ontology-Playground catalogue fixture (MIT)
docs/
├── architecture/
│   └── PRD.md                              # amend: §3.7 acceptance row, §13.4 section, Appendix B (new B.3 ADR)
│   └── decisions/
│       └── 0003-foxx-parity-retired.md     # NEW redirect stub, mirrors 0001/0002
└── howto/                                  # NEW top-level dir — none exists today
    ├── index.md
    ├── protege.md         # D-07, recorded transcript
    ├── yasgui.md          # D-07, recorded transcript
    ├── sparqlwrapper.md   # D-06, recipe mirrors the automated test's query
    ├── ontology-playground.md  # D-06
    ├── arq.md             # D-07, rsparql invocation + transcript
    ├── oxigraph.md        # optional, low-cost (already have pyoxigraph)
    └── arango-ontoextract.md   # D-03, deployment topology note (no live AOE)
```

### Pattern 1: Blank-node-safe triple-bag equality with `rdflib.compare`
**What:** Compare two RDF graphs for isomorphism (equal up to blank-node renaming) — exactly what D-03/§11.3's "triple-bag equality (modulo blank-node renaming)" requires.
**When to use:** The AOE own-half contract test and the Ontology Playground roundtrip test, for both Turtle and RDF/XML.
**Example:**
```python
# Verified by direct execution this session (rdflib 7.6.0 installed in the venv)
from rdflib import Graph

g1 = Graph()
g1.parse(data=original_owl, format="turtle")

g2 = Graph()
g2.parse(data=reexported_owl, format="xml")  # rdflib's format name for RDF/XML is "xml"

assert g1.isomorphic(g2)  # True even when blank-node IDs differ across the round-trip
```
`Graph.isomorphic()` is a thin wrapper over `rdflib.compare.to_isomorphic()` +
equality; both were exercised directly and returned `True` for a
Turtle→RDF/XML→rdflib round-trip in this session.

### Pattern 2: Deterministic schema activation for a live `/sparql` query
**What:** `POST /mapping/import-owl` and `POST /mapping/export-owl` are
**stateless** — they operate on the request body, not on the session/schema
cache (`arango_sparql/service/routes/mapping.py:521-533`, explicit
docstring: "Operates on the request body rather than session state because
the schema cache is per-DB, not per-session"). Meanwhile `POST /sparql`
(`arango_sparql/service/routes/protocol.py:1024`) resolves its schema via
`_resolve_protocol_session` + `_bundle_for_session`, which ultimately reads
from the same process-wide `SchemaCache` that `/schema/introspect` uses
(`arango_sparql/service/routes/schema.py:100` `_resolve_schema_cache()`).
There is no automatic wiring from "I just imported this OWL" to "the
`/sparql` endpoint now sees it."
**When to use:** The AOE roundtrip test needs the imported mapping to be
*queryable*, not just round-trippable. `SchemaCache.put()`
(`arango_sparql/schema/cache.py:207`) is the direct, deterministic way to do
this without depending on heuristic/analyzer auto-detection picking the
right physical shape from real collection contents.
**Example:**
```python
# Sketch — file:line references verified by reading the source this session
from arango_sparql.schema.cache import SchemaCache
from arango_sparql.service.routes.schema import _resolve_schema_cache

bundle = turtle_to_mapping(imported_owl_turtle)   # from POST /mapping/import-owl's own code path
_resolve_schema_cache().put(db_name, bundle)       # makes /sparql see it deterministically
# ... then POST /connect, then POST /sparql with ASK/SELECT
```

### Pattern 3: In-process perf harness reusing the existing fake-ArangoDB double
**What:** `tests/test_service_sparql_routes.py` already defines
`_FakeArangoClient` / `_FakeDb` / `_FakeCursor` and monkeypatches
`arango_sparql.service.ArangoClient` so `/connect` → `/translate` →
`/execute` run against `TestClient(app)` with **zero real network or Docker
dependency** (verified by reading `tests/test_service_sparql_routes.py:199-239`).
**When to use:** The three CI-gated perf rows (D-08). This resolves the
tension between `/execute`'s real `session.db.aql.execute(...)` call
(`arango_sparql/service/routes/sparql.py:265`) and D-08's "in-process"
framing — §9.4 itself defines the `/execute overhead` budget as
"translate + dispatch, **excluding** AQL exec," so stubbing the AQL call
entirely is the *correct* way to measure exactly what the SLO names, not a
workaround.
**Example:**
```python
# Sketch, mirroring tests/test_service_sparql_routes.py's existing fixtures
import time, statistics
from fastapi.testclient import TestClient
import arango_sparql.service as svc
from arango_sparql.service import app

def test_execute_overhead_p95(monkeypatch, fake_client_factory):
    monkeypatch.setattr(svc, "ArangoClient", fake_client_factory)  # existing double
    client = TestClient(app)
    token = _connect_session(client)  # existing helper pattern
    samples = []
    for _ in range(100):
        t0 = time.perf_counter()
        client.post("/execute", headers={"Authorization": f"Bearer {token}"},
                    json={"sparql": "ASK {?s ?p ?o}", "ontology_ttl": _MIN_TTL})
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=100)[93]
    assert p95 <= baseline_p95 * 1.25
```

### Pattern 4: Real bound HTTP server for `SPARQLWrapper` (not `TestClient`)
**What:** `SPARQLWrapper` makes real `urllib`-based HTTP requests to a URL
string; it has no ASGI-transport plug point, so `fastapi.testclient.TestClient`
(which never opens a real socket) cannot be its target. A background
`uvicorn.Server` thread, bound to `127.0.0.1:<port>`, is the standard way to
give a real HTTP client something in-process to talk to.
**When to use:** `tests/integration/test_sparqlwrapper_smoke.py`.
**Example:**
```python
# uvicorn 0.35.0's Config/Server API supports this; verified this session
# by introspecting the installed package's Config signature.
import threading, time, uvicorn
from arango_sparql.service import app

config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
while not server.started:
    time.sleep(0.05)
# server.servers[0].sockets[0].getsockname() gives the actual bound (host, port)
...
server.should_exit = True
thread.join(timeout=5)
```

### Anti-Patterns to Avoid
- **Don't try to make `SPARQLWrapper` talk to `TestClient(app)` via monkeypatched `urllib`.** It's fragile and diverges from testing what a real client actually does over the wire (headers, chunking, content negotiation). Bind a real port instead (Pattern 4) — it's still "in-process" in every sense that matters (same Python process, no container).
- **Don't assume `pyoxigraph` is required for the AOE roundtrip.** D-03 asks for our own routes' fidelity, not a third-party ground truth; `rdflib.compare` is sufficient and simpler. Reserve `pyoxigraph` for an optional secondary sanity check if the planner wants extra rigor.
- **Don't reuse the property-thin JSON schema fixtures** (`tests/schema/fixtures/pg.export.json` etc.) for the AOE roundtrip — they have empty `properties: []` conceptual blocks and are wire-dict shaped, not Turtle. The proven `_PERSON_ONTOLOGY_TTL`-style fixture (already round-tripped successfully through `turtle_to_mapping` → `/execute` in `tests/integration/test_execute_endpoint.py`) is the right base to extend.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Blank-node-safe RDF graph equality | A custom triple-set normalizer | `rdflib.Graph.isomorphic()` / `rdflib.compare.to_isomorphic()` | Graph isomorphism with blank nodes is a genuinely hard problem (subgraph-isomorphism-adjacent); rdflib's implementation is battle-tested and already a transitive dependency |
| p95/p99 latency percentiles | A manual sort-and-index percentile function | `statistics.quantiles(data, n=100)` (stdlib, Python ≥3.8) | Correct, no new dependency, consistent with this repo's existing "no scipy" convention (`tests/nl2sparql/eval/power.py`) |
| SPARQL client wire protocol (headers, result format negotiation, ASK boolean parsing) | A custom `requests`-based SPARQL client for the smoke test | `SPARQLWrapper` | It's the exact tool PRD §11.1 names as the compat target — the point of the test is to prove *this* client works, not a proxy for it |
| Live HTTP server for a real client in tests | A hand-rolled `socketserver`/raw-ASGI plumbing shim | `uvicorn.Server` run in a background thread | Already a core dependency; documented, standard pattern; avoids reinventing ASGI lifecycle handling |

**Key insight:** every "Don't Hand-Roll" item this phase already has a
library either installed or trivially addable — the phase's actual
difficulty is *wiring existing pieces together correctly* (which fixture
goes with which test, how schema activation actually works), not algorithmic
novelty.

## Common Pitfalls

### Pitfall 1: RDF/XML "coverage" silently degrading to a Turtle-only test
**What goes wrong:** A planner assumes `/mapping/import-owl` and
`/mapping/export-owl` already "handle RDF/XML" because PRD §11.3/§12.2 say
so, and writes the AOE/Playground tests only to discover at execution time
that `graph.parse(data=rdfxml_bytes, format="turtle")` (the current hardcoded
call) raises a parse error on RDF/XML input.
**Why it happens:** The PRD documents the *intended* v1.0 contract; the
`arango_sparql/translate/owl.py` implementation only ever grew a Turtle path.
Verified this session by reading `turtle_to_mapping()` (line 242:
`graph.parse(data=turtle, format="turtle")`), `mapping_to_turtle()` (line
470: `graph.serialize(format="turtle")`), and the route layer's
`_wants_turtle_response()`/`_read_import_body()`, none of which branch on any
other rdflib format string.
**How to avoid:** Budget an explicit, small task: add a format-dispatch table
(`{"text/turtle": "turtle", "application/rdf+xml": "xml", "application/x-turtle": "turtle", "application/ld+json": "json-ld", "application/n-triples": "nt"}`)
to both the import Content-Type sniff and the export Accept negotiation, and
thread a `format:` kwarg through `turtle_to_mapping`/`mapping_to_turtle`
(or new sibling functions). All four target formats are natively supported
by the installed rdflib 7.6 with no new dependency (verified by parsing
Turtle→RDF/XML, JSON-LD, and N-Triples samples directly this session).
**Warning signs:** Any AOE/Playground test that only ever exercises
`Accept: text/turtle` / `Content-Type: text/turtle` is not actually
satisfying D-04's "Turtle + RDF/XML at minimum" — check the test body for a
second, RDF/XML-content-typed request before considering the row done.

### Pitfall 2: Treating `/execute overhead` as truly dependency-free without stubbing the DB call
**What goes wrong:** A CI-gated perf test hits real `/execute` without
mocking `ArangoClient`, silently making the "in-process" perf job depend on
a live docker-compose ArangoDB service container in CI — which then either
(a) requires copying the `integration` CI job's service-container block
(defeating the "fast in-process" framing and budget) or (b) flakes/fails
when Docker isn't available on the runner.
**Why it happens:** `session.db.aql.execute(...)` genuinely reaches a real
database; PRD §9.4 calls the row "translate + dispatch, **excluding** AQL
exec," but that carve-out only holds if the test *implements* the exclusion
(e.g., a fake cursor that returns instantly) rather than merely trusting
that `RETURN 1` is "fast enough" over the wire.
**How to avoid:** Reuse `_FakeArangoClient`/`_FakeDb`/`_FakeCursor` from
`tests/test_service_sparql_routes.py` (already proven to drive the full
`/connect → /translate → /execute` path with zero real I/O) rather than
building new perf-specific test doubles.
**Warning signs:** A perf test file that imports `ArangoClient` from
`python-arango` directly, or that requires `RUN_INTEGRATION=1` / Docker to
run at all, is not actually satisfying D-08.

### Pitfall 3: Conflating the two different OWL fixtures needed
**What goes wrong:** Using one fixture for both the Ontology Playground
roundtrip (D-06) and the AOE own-half contract test (D-03), then discovering
the Playground fixture has no `phys:collectionName` annotations and can't
be pushed into a queryable `SchemaCache` entry, or that the AOE fixture is
JSON-wire-shaped and was never proven to round-trip through
`turtle_to_mapping`.
**Why it happens:** They test different contracts. The Playground roundtrip
is *pure OWL fidelity* — export → import → re-export → isomorphic, no
ArangoDB involved, no `phys:` annotations required. The AOE contract
additionally needs `ASK`/`SELECT` via `/sparql` to actually resolve to AQL
against a live collection, which requires `phys:` physical-mapping
annotations the Playground's `cosmic-coffee.rdf` doesn't carry.
**How to avoid:** Use the vendored `cosmic-coffee.rdf` (MIT, 349 triples,
verified fetchable from
`github.com/microsoft/Ontology-Playground/catalogue/official/cosmic-coffee/`)
for the Playground roundtrip only; extend the proven
`_PERSON_ONTOLOGY_TTL`-style `phys:`-annotated Turtle fixture (already used
in `tests/integration/test_execute_endpoint.py`) for the AOE contract test.
**Warning signs:** An AOE roundtrip test with no `phys:collectionName` (or
equivalent) annotation in its source fixture will fail to resolve at the
`/sparql` step, not at import/export.

### Pitfall 4: New `perf` pytest marker not registered
**What goes wrong:** Writing `pytestmark = pytest.mark.perf` in a new test
file without adding `"perf: ..."` to `pyproject.toml`'s `[tool.pytest.ini_options] markers` list triggers pytest's unregistered-marker warning (or a hard failure, depending on `--strict-markers`, which is not currently set but could be added).
**Why it happens:** `pyproject.toml`'s current marker list is only
`integration`, `w3c`, `cross`, `eval` (verified by reading `pyproject.toml`
this session) — PRD §13.1 documents `perf`, `bench`, `legacy_roundtrip`, and
`security` markers that were never actually registered, because no phase has
needed them yet.
**How to avoid:** Add `"perf: performance budget enforcement (see PRD §9.4); CI-blocking on >25% p95 regression for the fast in-process rows"` to the markers list as part of this phase's Wave 0. Do **not** add `legacy_roundtrip` (Foxx harness is retired, D-01/D-02) or `bench` (out of scope — PRD's `bench` marker is the *translator-only* gauge benchmark, a different, pre-existing concern not touched by this phase).

## Code Examples

### Verify RDF/XML round-trip fidelity (this session's actual verification, not a hypothetical)
```python
# Executed directly this session against the project's installed rdflib 7.6.0
from rdflib import Graph
g1 = Graph()
g1.parse(data=turtle_source, format="turtle")
g2 = Graph()
g2.parse(data=g1.serialize(format="xml"), format="xml")  # round-trip through RDF/XML
assert g1.isomorphic(g2)  # -> True
```

### Fetching the vendored Ontology Playground fixture
```bash
# MIT-licensed, verified via GitHub API this session (spdx_id: "MIT")
curl -sL \
  https://raw.githubusercontent.com/microsoft/Ontology-Playground/main/catalogue/official/cosmic-coffee/cosmic-coffee.rdf \
  -o tests/fixtures/cosmic_coffee.rdf
# 26,981 bytes; 349 triples; 6 owl:Class, 7 owl:ObjectProperty, 36 owl:DatatypeProperty
# (all counts verified by parsing the fetched file with rdflib this session)
```

### `rsparql` invocation for the Protégé documented-manual recipe
```bash
# Installed via `brew install jena` (6.1.0) and verified with --help this session:
#   rsparql --service URL [--results FORMAT] [--query FILENAME | QueryString]
#   Flags include: --results=<text|XML|JSON|CSV|TSV>, --post (force HTTP POST)
rsparql --service http://localhost:8001/sparql \
  --query 'PREFIX : <http://example.org/> SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }' \
  --results JSON

rsparql --service http://localhost:8001/sparql \
  --query 'ASK { ?s ?p ?o }'
```
Note: two related Apache Jena docs pages disagree slightly on the "official"
tool name for remote querying (`cmds.html` names `arq.remote`; the
`sparql-remote.html` page and this session's direct `brew install` +
`--help` both confirm the actual shipped binary is `rsparql`). Treat
`rsparql` as ground truth — it is what actually got installed and it is
what accepted `--service`/`--query`/`--results` flags when run this session.

### SPARQLWrapper against a real bound endpoint
```python
# API confirmed against sparqlwrapper.readthedocs.io/en/latest/main.html
from SPARQLWrapper import SPARQLWrapper, JSON, POST

sparql = SPARQLWrapper(f"http://127.0.0.1:{port}/sparql")
sparql.setMethod(POST)
sparql.setReturnFormat(JSON)
sparql.setQuery("SELECT ?s ?n WHERE { ?s a <http://example.org/Person> ; <http://example.org/name> ?n }")
results = sparql.query().convert()
assert "results" in results and "bindings" in results["results"]

sparql.setQuery("ASK { ?s ?p ?o }")
sparql.setReturnFormat(JSON)  # ASK JSON result carries {"boolean": true/false}
ask_result = sparql.query().convert()
assert isinstance(ask_result.get("boolean"), bool)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Legacy `arango-sparql` Foxx service as the parity ground truth (PRD §3.7/§13.4 as originally written) | W3C DAWG suite (96.4% query-eval coverage) as the sole correctness ground truth; Foxx parity retired via ADR | This phase (D-01/D-02) | Simpler v1.0 acceptance surface; removes a two-service Docker harness that would have needed the (now-absent from the workspace) legacy Foxx repo |
| Full two-service AOE Docker roundtrip (originally implied by §3.11/§13.4-adjacent framing) | Own-half contract test only — no external `arango-ontoextract` clone | This phase (D-03) | Removes a hard workspace dependency (the AOE repo isn't present locally — `references/arango-ontoextract` doesn't exist, only a dead symlink stub, consistent with the discussion log's framing note) |

**Deprecated/outdated:**
- `tests/legacy_roundtrip/` (PRD §13.4 module name) — will never be built; the PRD section describing it becomes historical-context-only after this phase's amendment.
- The `legacy_roundtrip` pytest marker (mentioned in PRD §13.1's test-category table) — should **not** be added to `pyproject.toml`'s markers list this phase, since no test will ever use it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact Apache Jena remote-query tool name is `rsparql` (not `arq` or `arq.remote`) | Code Examples, Standard Stack | Low — verified directly by installing via Homebrew and running `--help` this session; flagged only because two official doc pages used slightly different terminology for the same underlying tool |
| A2 | `SPARQLWrapper`'s ASK JSON result shape is `{"boolean": true/false}` under `setReturnFormat(JSON)` | Code Examples | Low-Medium — this is the standard SPARQL 1.1 Query Results JSON Format for ASK, and the project's own `/sparql` route already emits SPARQL-results-JSON per §5.2, but the exact key SPARQLWrapper's `.convert()` surfaces was not executed end-to-end against a running service this session (only read from official docs) — worth a quick smoke check in Wave 0 |
| A3 | `@matdata/yasgui` (npm, 5.20.3) is a reasonable current fork/successor to the original `@triply/yasgui` (4.2.28) for the YASGUI embed snippet | Standard Stack (implicitly, via WebSearch) | Low — YASGUI is documented-manual only (D-07), no automated test depends on the exact npm package chosen; worth a quick maintenance-status check before finalizing `docs/howto/yasgui.md` |

**If this table is empty:** N/A — see above; all three entries are low-risk verification gaps, not load-bearing unknowns.

## Open Questions

1. **Does the AOE contract test need seeded instance data, or is an empty-collection ASK/SELECT sufficient?**
   - What we know: `/execute` and (by inference) `/sparql` execute correctly against zero-row collections, returning well-formed empty results — this alone proves the AQL-emission path is correct.
   - What's unclear: Whether D-03's "ASK/SELECT via /sparql" intends a purely structural smoke check (query executes, returns correctly-typed empty results) or wants at least one seeded document so a SELECT returns a non-empty binding and an ASK returns `true` at least once.
   - Recommendation: Mirror `tests/integration/test_execute_endpoint.py`'s `_seeded_collection` pattern (create the collection, insert 1-3 documents) — it's already proven, costs almost nothing extra, and produces a strictly more convincing contract test (both a `true` and a `false` ASK, and a non-empty SELECT).

2. **Should the RDF/XML format-plumbing fix land as part of this phase, or as a fast-follow prerequisite phase/task?**
   - What we know: It's a small, mechanical, rdflib-native change (format dispatch table) with zero new dependencies, verified feasible this session.
   - What's unclear: The phase framing explicitly says "builds verification harnesses... not new product features," which could be read as forbidding any production code change at all.
   - Recommendation: Frame it explicitly to the planner as "closing a documented-but-unimplemented PRD contract" (§11.3/§12.2 already assert RDF/XML support exists) rather than "new feature" — the alternative (testing only Turtle and silently not satisfying D-04) would leave a known gap between the PRD and the shipped behavior. This should be an explicit, small, separately-reviewable task, not folded silently into the test-writing tasks.

3. **What is the right sample size / warmup policy for the CI-gated perf p95 gate to stay stable on shared GitHub Actions runners?**
   - What we know: D-08 already asks for a "generous" tolerance (the existing 25% from §9.4); `statistics.quantiles` needs a reasonably large N for a stable p95 estimate (N=100 gives whole-percentile granularity).
   - What's unclear: The exact N and whether a warmup discard (e.g., first 10 iterations excluded) is needed to avoid cold-JIT/cold-cache skew — Python has no JIT to warm up (interpreter, not PyPy), but rdflib/pydantic model construction and FastAPI's routing table lookups may still have first-call overhead worth discarding.
   - Recommendation: N=100-200 samples with the first 10-20 discarded as warmup, consistent with the `/translate cold` vs `/translate warm` SLO rows already distinguishing this exact effect in §9.4's own table.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker / `docker compose` | AOE roundtrip, SPARQLWrapper smoke, Ontology Playground roundtrip (all Docker-gated per D-06), report-only perf rows | ✓ (assumed present on CI per existing `integration` job; present on this research machine via `docker-compose.yml`'s existing usage) | N/A | `tests/integration/conftest.py`'s existing best-effort skip (`try_boot_arangodb_via_compose` → `pytest.skip`) already covers "Docker absent" cleanly — reuse it |
| `SPARQLWrapper` (PyPI) | SPARQLWrapper smoke test | ✗ (not currently installed/declared) | 2.0.0 latest | None needed — trivial `pip install` |
| Apache Jena / `rsparql` | `docs/howto/arq.md` recorded transcript (D-07, human-run only, never CI) | ✓ verified installable via `brew install jena` (6.1.0) this session | 6.1.0 | Official Apache tarball if Homebrew unavailable |
| Protégé (JVM desktop app) | `docs/howto/protege.md` recorded transcript (D-07, human-run only) | Not verified this session (GUI app, no CLI check) | 5.x per PRD §11.1 | N/A — documented-manual, human downloads it |
| A modern browser | `docs/howto/yasgui.md` recorded transcript (D-07, human-run only) | N/A (human-run) | N/A | N/A |
| `uvicorn` | Live-bound-server fixture for `SPARQLWrapper` test | ✓ already a core dependency | 0.35.0 installed | N/A |

**Missing dependencies with no fallback:** none — every missing piece (`SPARQLWrapper`) is a trivial `pip install`, and Docker-absence is already handled by the existing skip convention.

**Missing dependencies with fallback:** none beyond what's listed above.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` (only runner per `.cursor/rules/200-testing.mdc`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — markers list needs a new `perf` entry this phase (see Pitfall 4) |
| Quick run command | `pytest -m "not integration and not w3c and not eval and not perf" --tb=short -q` (mirrors the existing CI `test` job) |
| Full suite command | `RUN_INTEGRATION=1 pytest tests/integration tests/cross tests/perf --tb=short -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-foxx-parity | ADR + doc amendment only, no test | n/a (documentation) | n/a | n/a — PRD/ROADMAP/REQUIREMENTS.md edits |
| REQ-thirdparty-tool-compat (SPARQLWrapper) | SELECT + ASK + Service Description over a real bound HTTP server | integration | `RUN_INTEGRATION=1 pytest tests/integration/test_sparqlwrapper_smoke.py -m integration -q` | ❌ Wave 0 |
| REQ-thirdparty-tool-compat (Ontology Playground) | File-based OWL export→import→re-export→isomorphic | integration | `RUN_INTEGRATION=1 pytest tests/integration/test_ontology_playground_roundtrip.py -m integration -q` | ❌ Wave 0 |
| REQ-thirdparty-tool-compat (Protégé, YASGUI) | Documented-manual recorded transcript | manual-only (justified: D-07, no CI image) | n/a | ❌ Wave 0 (`docs/howto/` files) |
| REQ-ontoextract-integration | export-owl → import-owl isomorphism + ASK/SELECT via `/sparql` | integration | `RUN_INTEGRATION=1 pytest tests/integration/test_aoe_roundtrip.py -m integration -q` | ❌ Wave 0 |
| REQ-performance-slos (3 CI-gated rows) | p95 within 25% of baseline, in-process | perf (new marker) | `pytest tests/perf/test_translate_latency.py tests/perf/test_execute_overhead.py -m perf -q` | ❌ Wave 0 |
| REQ-performance-slos (8 report-only rows) | p95/memory/concurrency measured, written to `LATENCY_REPORT.md`, never gates | perf (new marker, non-blocking) or manual-only for `/nl-translate` | `RUN_INTEGRATION=1 pytest tests/perf -m perf -k "not translate_latency and not execute_overhead" -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest -m "not integration and not w3c and not eval and not perf" -q` (existing fast default; unaffected by this phase's additions)
- **Per wave merge:** `RUN_INTEGRATION=1 pytest tests/integration tests/perf -q` plus a manual run of the two `docs/howto/` recorded-transcript recipes
- **Phase gate:** `pytest tests/perf -m perf -k "translate_latency or execute_overhead"` green (CI-blocking) before `/gsd-verify-work`; the 8 report-only rows produce a fresh `LATENCY_REPORT.md` reviewed by a human, not gated

### Wave 0 Gaps
- [ ] `pyproject.toml` — register the `perf` marker
- [ ] `tests/perf/__init__.py` + `tests/perf/conftest.py` — new directory, no existing scaffolding
- [ ] `tests/perf/baseline.json` — first-run capture, checked in after human review (mirrors `tests/nl2sparql/eval/baseline.json`'s established convention)
- [ ] `docs/howto/` — directory does not exist yet (verified this session — `ls docs/howto` returns nothing)
- [ ] RDF/XML format-plumbing fix in `arango_sparql/translate/owl.py` + `arango_sparql/service/routes/mapping.py` — blocks the RDF/XML row of both the AOE and Ontology Playground tests (see Pitfall 1)
- [ ] `SPARQLWrapper` added as a test/dev dependency in `pyproject.toml`
- [ ] `tests/fixtures/cosmic_coffee.rdf` — vendor the fetched MIT fixture with a `NOTICE.md`-style provenance note (mirrors the `tests/nl2sparql/eval/vendored/*/NOTICE.md` convention already established in Phase 07.1)

*(No existing test infrastructure covers any of Phase 4's requirements — this is a from-scratch build within an otherwise mature test suite.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No new surface | Existing session/Basic-auth handling (Phase 3, unchanged) covers the `/connect` calls these tests make |
| V3 Session Management | No new surface | Existing session token mechanism reused as-is by all new tests |
| V4 Access Control | No new surface | Existing tenant/session scoping unaffected |
| V5 Input Validation | Yes — the RDF/XML format-plumbing fix (Pitfall 1) is new parsing surface | The existing OWL-bomb triple-cap (`OwlBombError`, PRD §8.6 T7, `MAPPING_IMPORT_MAX_TRIPLES`) already applies uniformly regardless of source format since it counts triples post-parse — **verify this session's planned format-dispatch addition doesn't bypass that check for the new RDF/XML/JSON-LD/N-Triples paths** (it shouldn't, since the cap is applied to the parsed `Graph`, not the input bytes, but this is worth an explicit test) |
| V6 Cryptography | No new surface | N/A |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| RDF/XML entity-expansion ("billion laughs" via XML entities) reaching the new RDF/XML parse path | Denial of Service | rdflib's RDF/XML parser is built on Python's stdlib `xml.sax`, which by default does not expand external entities dangerously the way some XML libraries do, but this should be explicitly verified once the format-dispatch fix lands — add a test mirroring the existing `tests/security/test_owl_bomb.py` pattern but posting RDF/XML instead of Turtle, confirming the same `E_OWL_TOO_LARGE`/`OwlBombError` path triggers |
| A malicious `cosmic-coffee.rdf`-shaped fixture (supply-chain: vendoring a fetched file) | Tampering | Fixture is vendored (checked into the repo after this session's direct fetch+inspection), not fetched at test-time from the live GitHub URL — pin to a specific commit SHA and record it in a `NOTICE.md`, mirroring the `tests/nl2sparql/eval/vendored/*/NOTICE.md` convention (MIT license confirmed via GitHub API `license.spdx_id` this session) |

## Sources

### Primary (HIGH confidence — verified by direct execution or direct file reads this session)
- This repo's own source: `arango_sparql/translate/owl.py`, `arango_sparql/service/routes/mapping.py`, `arango_sparql/service/routes/schema.py`, `arango_sparql/service/routes/protocol.py`, `arango_sparql/service/routes/sparql.py`, `arango_sparql/schema/cache.py`, `tests/test_service_sparql_routes.py`, `tests/integration/test_execute_endpoint.py`, `tests/integration/conftest.py`, `tests/cross/*`, `tests/helpers/oxi.py`, `docs/architecture/PRD.md` (§3, §9.4, §11, §12.2, §13), `docs/architecture/decisions/0001-*.md`, `pyproject.toml`, `docker-compose.yml`
- Direct tool execution: `rdflib` 7.6.0 (isomorphic round-trip Turtle↔RDF/XML↔JSON-LD↔N-Triples), `pyoxigraph` 0.5.9 (`RdfFormat` enum), `uvicorn` 0.35.0 (`Config` signature), `slopcheck scan --pkg pypi` (SPARQLWrapper, pytest-benchmark), `pip index versions` (SPARQLWrapper, pytest-benchmark, rank_bm25), `brew install jena` + `rsparql --help` (6.1.0)
- GitHub API (`api.github.com/repos/microsoft/Ontology-Playground/...`) — fixture file listing, license (`spdx_id: MIT`), and the fetched `cosmic-coffee.rdf` itself (349 triples, verified via rdflib parse)

### Secondary (MEDIUM confidence — WebFetch/WebSearch against official docs, cross-checked)
- [sparqlwrapper.readthedocs.io/en/latest/main.html](https://sparqlwrapper.readthedocs.io/en/latest/main.html) — SPARQLWrapper API surface
- [pytest-benchmark.readthedocs.io](https://pytest-benchmark.readthedocs.io/en/latest/comparing.html) / [usage.html](https://pytest-benchmark.readthedocs.io/en/latest/usage.html) — stats surface, baseline comparison, `--benchmark-compare-fail` syntax
- [jena.apache.org/documentation/query/cmds.html](https://jena.apache.org/documentation/query/cmds.html), [sparql-remote.html](https://jena.apache.org/documentation/query/sparql-remote.html) — Apache Jena CLI tool docs (cross-checked against this session's direct `brew install` + `--help`, which is the tie-breaker where the two doc pages used different tool names)

### Tertiary (LOW confidence — WebSearch only, flagged in Assumptions Log)
- `@matdata/yasgui` npm package as a current YASGUI fork/successor (A3)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version number was read from the installed venv or the live PyPI registry this session, not recalled from training data
- Architecture: HIGH — every architectural claim (stateless mapping routes, `/execute`'s real DB dependency, `SchemaCache.put()`, `_FakeArangoClient`) is a direct file read with a file:line citation, not an inference
- Pitfalls: HIGH — all four pitfalls were discovered by reading actual code, not hypothesized

**Research date:** 2026-07-27
**Valid until:** 30 days (stable — no fast-moving external dependency; the one YASGUI-package assumption is the only item likely to drift faster)
