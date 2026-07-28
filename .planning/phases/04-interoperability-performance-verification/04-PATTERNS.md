# Phase 4: Interoperability & performance verification - Pattern Map

**Mapped:** 2026-07-27
**Files analyzed:** 20 (14 new, 6 modified)
**Analogs found:** 18 / 20 (2 no-analog: brand-new `docs/howto/` prose and the ADR content itself)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `arango_sparql/translate/owl.py` (MODIFY: RDF/XML+JSON-LD+N-Triples dispatch) | service/utility (rdflib format dispatch) | transform | same file, `turtle_to_mapping()`/`mapping_to_turtle()` (self-analog — extend existing function signatures) | exact |
| `arango_sparql/service/routes/mapping.py` (MODIFY: Content-Type/Accept dispatch) | route/controller | request-response | same file, `_read_import_body()` / `_wants_turtle_response()` (self-analog — extend the existing sniff/negotiate helpers) | exact |
| `tests/integration/test_aoe_roundtrip.py` (NEW) | test (integration) | CRUD (import→export→query) | `tests/integration/test_execute_endpoint.py` | exact |
| `tests/integration/test_sparqlwrapper_smoke.py` (NEW) | test (integration) | request-response (real HTTP client) | `tests/integration/test_execute_endpoint.py` (boot/skip pattern) + `tests/test_service_sparql_routes.py` (route contract) | role-match (new live-server-thread wiring not present anywhere yet) |
| `tests/integration/test_ontology_playground_roundtrip.py` (NEW) | test (integration, file-based) | transform (round-trip) | `tests/cross/test_minus_exists_cross.py` (isomorphism-style oracle comparison) + `tests/test_service_sparql_routes.py` (route call shape) | role-match |
| `tests/perf/__init__.py` (NEW) | test scaffolding | n/a | `tests/cross/__init__.py` (empty init) | exact |
| `tests/perf/conftest.py` (NEW) | test fixture/utility | request-response (in-process double) | `tests/test_service_sparql_routes.py` `_FakeArangoClient`/`_FakeDb`/`_FakeCursor`/`fake_client_factory` (lines 96-239) | exact |
| `tests/perf/test_translate_latency.py` (NEW) | test (perf, CI-gated) | request-response | `tests/test_service_sparql_routes.py` (TestClient + fake double pattern) | role-match |
| `tests/perf/test_execute_overhead.py` (NEW) | test (perf, CI-gated) | request-response | `tests/test_service_sparql_routes.py` `_FakeArangoClient` (same double, `/execute` path) | exact |
| `tests/perf/baseline.json` (NEW) | config/fixture (checked-in baseline) | batch | `tests/nl2sparql/eval/baseline.json` | exact |
| `tests/perf/LATENCY_REPORT.md` (NEW, generated) | generated artifact | batch | `tests/nl2sparql/eval/reports/` convention (generated, human-reviewed) | role-match |
| `tests/fixtures/cosmic_coffee.rdf` (NEW, vendored) | fixture | file-I/O | `tests/nl2sparql/eval/vendored/ck25/raw/*` + its `NOTICE.md` | exact |
| `tests/fixtures/NOTICE.md` or `tests/fixtures/cosmic_coffee.NOTICE.md` (NEW, provenance) | doc/config | n/a | `tests/nl2sparql/eval/vendored/ck25/NOTICE.md` | exact |
| `docs/howto/index.md`, `protege.md`, `yasgui.md`, `sparqlwrapper.md`, `ontology-playground.md`, `arq.md` (NEW dir) | documentation | n/a | PRD §11.4 "Connectivity recipes (`docs/howto/`)" (spec only — no existing files) | no analog (net-new doc convention; use PRD §11.1-§11.4 prose as source content) |
| `pyproject.toml` (MODIFY: `perf` marker + SPARQLWrapper dev dep) | config | n/a | same file, `[tool.pytest.ini_options] markers` list (line 97) + `[project.optional-dependencies].dev` (lines ~78-89) | exact |
| `docs/architecture/decisions/0003-foxx-parity-retired.md` (NEW stub) | documentation (ADR redirect stub) | n/a | `docs/architecture/decisions/0001-named-graphs-per-document.md` (redirect-stub pattern) | exact |
| `docs/architecture/PRD.md` (MODIFY: new Appendix B.3, §3.7/§13.4/§9.4 amendments) | documentation | n/a | same file, Appendix B.2 (ADR-0002, lines 3606-3684) for ADR body shape; §13.4 (lines 2228-2247) for the section being retired | exact |
| `.planning/ROADMAP.md` (MODIFY: strike SC1, Phase 4 block) | documentation | n/a | same file, Phase 4 block (lines 86-99) | exact |
| `.planning/REQUIREMENTS.md` (MODIFY: retire REQ-foxx-parity) | documentation | n/a | same file, lines 35-38 & 110-113 | exact |
| `docker-compose.yml` (read-only reference, not modified) | config | n/a | n/a | n/a |

## Pattern Assignments

### `arango_sparql/translate/owl.py` (service/utility, transform) — MODIFY

**Analog:** itself — extend `turtle_to_mapping()` / `mapping_to_turtle()` rather than fork new functions, per Pitfall 1 in RESEARCH.md.

**Current hardcoded call sites to change** (both verified this session by direct read):
```python
# turtle_to_mapping() — line 242
graph.parse(data=turtle, format="turtle")

# mapping_to_turtle() — line 470
return graph.serialize(format="turtle")

# export_owl() route re-import roundtrip — arango_sparql/service/routes/mapping.py:415
roundtrip.parse(data=turtle, format="turtle")
```

**Error-type pattern to reuse** (lines 116-136 — do NOT invent new exception classes, thread the existing two through the new format paths):
```python
class OwlBombError(SparqlError):
    code = "E_OWL_TOO_LARGE"

class OwlParseError(SparqlError):
    code = "E_OWL_PARSE"
```

**Recommended format-dispatch table** (RESEARCH.md Pitfall 1, already vetted against installed rdflib 7.6 — copy verbatim):
```python
_FORMAT_ALIASES: dict[str, str] = {
    "text/turtle": "turtle",
    "application/x-turtle": "turtle",
    "application/rdf+xml": "xml",       # rdflib's format name for RDF/XML is "xml"
    "application/ld+json": "json-ld",
    "application/n-triples": "nt",
}
```
Thread a `format: str = "turtle"` kwarg through `turtle_to_mapping()`/`mapping_to_turtle()` (or add `owl_format_from_mapping()`-style siblings) — do not duplicate the whole function body per format.

**Triple-cap invariant to preserve** (Security §V5 in RESEARCH.md): the cap in `turtle_to_mapping()` (lines 246-253) is applied to `count_triples(graph)` **after** `graph.parse(...)` regardless of format, so extending the `format=` kwarg does not require touching the cap logic — verify with a new test mirroring `tests/security/test_owl_bomb.py`'s Turtle case but posting `application/rdf+xml`.

---

### `arango_sparql/service/routes/mapping.py` (route/controller, request-response) — MODIFY

**Analog:** itself — extend `_read_import_body()` and `_wants_turtle_response()`.

**Content-Type sniff pattern to extend** (lines 148-197, `_read_import_body`):
```python
content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
if content_type in ("application/json", ""):
    ...  # JSON envelope path — unchanged
# Treat any non-JSON content as raw Turtle today — this branch needs a
# format-dispatch lookup (see owl.py's _FORMAT_ALIASES) instead of a
# blanket "decode as Turtle" assumption.
try:
    return raw.decode("utf-8"), None
```

**Accept-header negotiation pattern to extend** (lines 200-213, `_wants_turtle_response`):
```python
def _wants_turtle_response(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    if not accept or accept == "*/*":
        return False
    return "text/turtle" in accept or "application/x-turtle" in accept
```
Generalize to return the negotiated *format name* (not just a bool) so `export_owl()` can call `graph.serialize(format=negotiated)` and set the matching `Content-Type` (`application/rdf+xml` for `format="xml"`, etc.) instead of always responding `text/turtle`.

**Error-handling envelope to mirror for every new branch** (lines 251-293, exception→HTTPException mapping — copy this shape for any new parse-format error):
```python
try:
    bundle = turtle_to_mapping(turtle, source_notes=effective_notes)
except OwlBombError as exc:
    raise HTTPException(status_code=422, detail={"error": _sanitize_error(str(exc)), "code": exc.code}) from exc
except OwlParseError as exc:
    raise HTTPException(status_code=422, detail={"error": _sanitize_error(str(exc)), "code": exc.code}) from exc
```

---

### `tests/integration/test_aoe_roundtrip.py` (test, CRUD/Docker-gated) — NEW

**Analog:** `tests/integration/test_execute_endpoint.py` (full file read, 271 lines).

**Boot/skip pattern to copy verbatim** (lines 36-129 — `_ARANGO_*` constants, `_arangodb_reachable()`, `_try_boot_arangodb_via_compose()`, `_live_arango` module-scoped fixture): reuse **as-is** by importing from `tests.integration.conftest` (`ensure_test_database`, `integration_enabled`, `arangodb_reachable`, `try_boot_arangodb_via_compose`) rather than re-copy-pasting the private helpers — `conftest.py`'s docstring explicitly says other modules should import its functions.

**Fixture extension pattern — `phys:`-annotated Turtle** (lines 55-73, `_PERSON_ONTOLOGY_TTL`): extend this exact fixture shape (don't invent a new one) so the AOE contract test has `phys:collectionName` annotations that make the imported mapping queryable:
```python
_PERSON_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
:Person a owl:Class ;
    phys:collectionName "Person" .
:name a owl:DatatypeProperty ;
    rdfs:domain :Person ; rdfs:range xsd:string .
"""
```

**Seeded-collection pattern to copy** (lines 132-170, `_seeded_collection` fixture — drop/recreate + insert_many + teardown).

**`/connect` helper to copy** (lines 173-191, `_connect_session`).

**New wiring this test needs beyond the analog (from RESEARCH.md Pattern 1 & 2):**
```python
from rdflib import Graph
from arango_sparql.schema.cache import SchemaCache  # or via _resolve_schema_cache()
from arango_sparql.service.routes.schema import _resolve_schema_cache
from arango_sparql.translate.owl import turtle_to_mapping

# 1. POST /mapping/import-owl (Turtle, then RDF/XML) -> bundle
# 2. POST /mapping/export-owl (Accept: text/turtle, then application/rdf+xml)
# 3. rdflib.Graph.isomorphic() triple-bag equality (blank-node-safe):
g1 = Graph(); g1.parse(data=original, format="turtle")
g2 = Graph(); g2.parse(data=reexported, format="xml")
assert g1.isomorphic(g2)
# 4. _resolve_schema_cache().put(db_name, bundle)  # deterministic activation
# 5. POST /connect -> POST /sparql {ASK/SELECT}
```

---

### `tests/integration/test_sparqlwrapper_smoke.py` (test, request-response/Docker-gated) — NEW

**Analog:** `tests/integration/test_execute_endpoint.py` (boot/skip + `_connect_session`) — no existing file provides the live-uvicorn-thread piece, so that part is genuinely new (see RESEARCH.md Pattern 4, already vetted this session).

**Live-server fixture (net-new — no existing analog, copy this verified sketch):**
```python
import threading, time, uvicorn
from arango_sparql.service import app

config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
while not server.started:
    time.sleep(0.05)
host, port = server.servers[0].sockets[0].getsockname()
...
server.should_exit = True
thread.join(timeout=5)
```

**SPARQLWrapper client pattern (verified against sparqlwrapper.readthedocs.io):**
```python
from SPARQLWrapper import SPARQLWrapper, JSON, POST
sparql = SPARQLWrapper(f"http://127.0.0.1:{port}/sparql")
sparql.setMethod(POST)
sparql.setReturnFormat(JSON)
sparql.setQuery("SELECT ?s ?n WHERE { ?s a <http://example.org/Person> ; <http://example.org/name> ?n }")
results = sparql.query().convert()
assert "results" in results and "bindings" in results["results"]
```
Reuse the boot/skip + `_connect_session` + `_seeded_collection` machinery from `test_execute_endpoint.py` first so the bound server has a real session+schema to query against.

**Anti-pattern flagged in RESEARCH.md:** do not attempt to point `SPARQLWrapper` at `fastapi.testclient.TestClient(app)` — it has no real socket. Always bind a real port.

---

### `tests/integration/test_ontology_playground_roundtrip.py` (test, transform, Docker-gated per D-06) — NEW

**Analog:** `tests/cross/test_minus_exists_cross.py` for the "compare against an oracle" shape (pyoxigraph `isomorphic`-adjacent pattern), plus `tests/test_service_sparql_routes.py` for the route-call idiom (`client.post("/mapping/import-owl", ...)`).

**Core pattern (file-based, no live SPARQL — RESEARCH.md Architecture Diagram §C):**
```python
fixture_bytes = (Path(__file__).parents[1] / "fixtures" / "cosmic_coffee.rdf").read_bytes()
resp = client.post("/mapping/import-owl", content=fixture_bytes,
                    headers={"Content-Type": "application/rdf+xml", "Authorization": f"Bearer {token}"})
bundle_wire = resp.json()["mapping"]
resp2 = client.post("/mapping/export-owl", json={"mapping": bundle_wire},
                     headers={"Accept": "application/rdf+xml", "Authorization": f"Bearer {token}"})
g1 = Graph(); g1.parse(data=fixture_bytes, format="xml")
g2 = Graph(); g2.parse(data=resp2.text, format="xml")
assert g1.isomorphic(g2)
```
**Pitfall 3 warning (RESEARCH.md):** do NOT reuse this fixture for the AOE contract test — `cosmic_coffee.rdf` has no `phys:collectionName` annotations and cannot resolve at `/sparql`. Keep the two fixtures and two tests strictly separate.

---

### `tests/perf/__init__.py` — NEW

**Analog:** `tests/cross/__init__.py` (0 lines — empty file, just makes the directory a package).

---

### `tests/perf/conftest.py` (test fixture/utility) — NEW

**Analog:** `tests/test_service_sparql_routes.py` lines 89-239 (`_FakeCursor`, `_FakeAql`, `_FakeDb`, `_FakeArangoClient`, `fake_client_factory` fixture) — copy this double **verbatim** (import it directly if perf tests can import from the test module, or duplicate the ~140-line block into `conftest.py` if cross-directory pytest imports are awkward — prefer `from tests.test_service_sparql_routes import _FakeArangoClient, fake_client_factory` if that import path works cleanly, else copy).

**Full excerpt to copy (lines 199-239):**
```python
class _FakeArangoClient:
    instances: list[_FakeArangoClient] = []
    def __init__(self, hosts: str = "") -> None:
        self.hosts = hosts
        self.db_calls: list[tuple[str, str | None, str | None]] = []
        self._dbs: dict[str, _FakeDb] = {}
        _FakeArangoClient.instances.append(self)
    def db(self, name, username=None, password=None) -> _FakeDb:
        self.db_calls.append((name, username, password))
        if name not in self._dbs:
            self._dbs[name] = _FakeDb(name)
        return self._dbs[name]
    def close(self) -> None:
        pass

@pytest.fixture
def fake_client_factory(monkeypatch: pytest.MonkeyPatch):
    _FakeArangoClient.instances.clear()
    monkeypatch.setattr(svc, "ArangoClient", _FakeArangoClient)
    monkeypatch.setenv("ARANGO_SPARQL_CONNECT_ALLOWED_HOSTS", "localhost,127.0.0.1")
    return _FakeArangoClient
```

**Percentile helper (stdlib, no new dependency — RESEARCH.md "Don't Hand-Roll"):**
```python
import statistics
p95 = statistics.quantiles(samples, n=100)[93]
```

---

### `tests/perf/test_translate_latency.py` and `tests/perf/test_execute_overhead.py` (test, perf CI-gated, D-08) — NEW

**Analog:** `tests/test_service_sparql_routes.py` (TestClient + fake-double wiring) combined with RESEARCH.md Pattern 3 (already-vetted sketch):
```python
import time, statistics
from fastapi.testclient import TestClient
import arango_sparql.service as svc
from arango_sparql.service import app

pytestmark = pytest.mark.perf  # new marker — must be registered in pyproject.toml

def test_execute_overhead_p95(monkeypatch, fake_client_factory):
    monkeypatch.setattr(svc, "ArangoClient", fake_client_factory)
    client = TestClient(app)
    token = _connect_session(client)  # mirror tests/integration/test_execute_endpoint.py's helper
    samples = []
    for _ in range(120):
        t0 = time.perf_counter()
        client.post("/execute", headers={"Authorization": f"Bearer {token}"},
                    json={"sparql": "ASK {?s ?p ?o}", "ontology_ttl": _MIN_TTL})
        samples.append((time.perf_counter() - t0) * 1000)
    samples = samples[20:]  # discard warmup per RESEARCH.md Open Question 3
    p95 = statistics.quantiles(samples, n=100)[93]
    baseline = json.loads((Path(__file__).parent / "baseline.json").read_text())
    assert p95 <= baseline["execute_overhead_p95_ms"] * 1.25
```

**Pitfall 2 (RESEARCH.md, critical):** do NOT hit real `/execute` without the `_FakeArangoClient` monkeypatch — `session.db.aql.execute(...)` (`arango_sparql/service/routes/sparql.py:265`) is a genuine live-DB call; without the fake double this "in-process" perf row silently becomes Docker-dependent.

---

### `tests/perf/baseline.json` (config/fixture, checked-in) — NEW

**Analog:** `tests/nl2sparql/eval/baseline.json` (structure: `generated_at` timestamp + nested per-config/per-case results — mirror the top-level shape, not the exact keys):
```json
{
  "generated_at": "2026-07-27T00:00:00Z",
  "rows": {
    "translate_cold_p95_ms": 42.0,
    "translate_warm_p95_ms": 8.0,
    "execute_overhead_p95_ms": 15.0
  }
}
```
Only the three CI-gated rows belong here (D-08); the 8 report-only rows go to `LATENCY_REPORT.md` instead, never to this gating baseline.

---

### `tests/fixtures/cosmic_coffee.rdf` + provenance note — NEW

**Analog:** `tests/nl2sparql/eval/vendored/ck25/NOTICE.md` (full file read — copy the section structure: Title / Source / Commit / License / Files vendored / Changes made / Downstream use).
```markdown
# Microsoft Ontology Playground — cosmic-coffee fixture — Attribution Notice

- **Title:** cosmic-coffee.rdf (Ontology Playground catalogue)
- **Source:** https://github.com/microsoft/Ontology-Playground
- **Commit:** <pin the exact SHA fetched this session>
- **License:** MIT (verified via GitHub API `license.spdx_id` this session)

## Files vendored
- `cosmic_coffee.rdf` — verbatim copy, 26,981 bytes / 349 triples ...

## Downstream use
`tests/integration/test_ontology_playground_roundtrip.py` round-trips this
fixture through `/mapping/import-owl` -> `/mapping/export-owl` and asserts
`rdflib.Graph.isomorphic()` equality (D-06).
```
Security note (RESEARCH.md Known Threat Patterns): pin to a commit SHA rather than fetching live at test time — this is a supply-chain control, not optional.

---

### `pyproject.toml` (config) — MODIFY

**Analog:** itself, `[tool.pytest.ini_options] markers` (line 97) and `[project.optional-dependencies].dev` (lines ~78-89).

**Markers list — add exactly one new entry, do not add `legacy_roundtrip`/`bench`:**
```toml
markers = [
  "integration: requires a running ArangoDB (see README); use docker-compose.yml",
  "w3c: SPARQL 1.1 W3C DAWG evaluation harness",
  "cross: cross-validates transpiled AQL bindings against pyoxigraph as the W3C reference store",
  "eval: NL->SPARQL evaluation harness; slow, gated behind RUN_EVAL=1",
  "perf: performance budget enforcement (see PRD §9.4); CI-blocking on >25% p95 regression for the fast in-process rows",
]
```

**Dev dependency addition — mirror the existing `pyoxigraph` comment-then-pin style:**
```toml
dev = [
  ...
  # SPARQLWrapper is the exact client PRD §11.1 names as the automated
  # third-party-tool compat target (D-06).
  "SPARQLWrapper>=2.0.0",
]
```

---

### `docs/architecture/decisions/0003-foxx-parity-retired.md` (NEW ADR stub) — NEW

**Analog:** `docs/architecture/decisions/0001-named-graphs-per-document.md` (full file, 8 lines — the entire redirect-stub convention):
```markdown
# ADR-0003: Legacy Foxx parity retired (Foxx deprecated)

> **Moved.** This ADR has been consolidated into the single
> source-of-truth PRD. See
> **[`PRD.md` → Appendix B.3](../PRD.md#b3-adr-0003--legacy-foxx-parity-retired-foxx-deprecated)**.
>
> This stub is kept only so existing links keep resolving. Do not add
> content here — all decisions live in [`PRD.md`](../PRD.md).
```
The **real ADR content** goes into `docs/architecture/PRD.md` Appendix B (new `### B.3` section), mirroring the `### B.2 ADR-0002` structure (Status / Date / Owner / Related code bullet list, then a prose "Context" section) — see next entry.

---

### `docs/architecture/PRD.md` (documentation) — MODIFY

**Analog:** same file, `### B.2 ADR-0002` (lines 3606-3684) for the new `### B.3` ADR's header shape:
```markdown
### B.3 ADR-0003 — Legacy Foxx parity retired (Foxx deprecated)

- **Status:** **Resolved — retired, not built.** Legacy Foxx `arango-sparql`
  is deprecated; W3C DAWG suite (≥96.4% query-eval coverage) is the sole
  correctness ground truth going forward.
- **Date:** 2026-07-27 — **Owner:** arango-sparql-py
- **Related sections:** §3.7 (waived), §13.4 (describes the retired harness)
```

**§13.4 (lines 2228-2247) amendment:** replace the "Module: `tests/legacy_roundtrip/`... " body with a short historical note: "This section described a harness retired by ADR-0003 (Appendix B.3) — never built. REQ-foxx-parity is retired; W3C DAWG coverage (§13.5) is the sole correctness gate."

**§9.4 amendment:** annotate each of the 11 SLO rows with its enforcement tier (CI-blocking vs report-only) per D-08/D-09 — do not delete rows, just add a column/footnote.

---

### `.planning/ROADMAP.md` (documentation) — MODIFY

**Analog:** same file, Phase 4 block (lines 86-99). Strike Success Criterion 1 verbatim:
```diff
-  1. ≥ 90% of translatable legacy Foxx fixtures pass a golden emitting semantically equivalent AQL (`test_foxx_roundtrip.py`, Docker-gated)
+  ~~1. ≥ 90% of translatable legacy Foxx fixtures...~~ **STRUCK — REQ-foxx-parity retired via ADR-0003 (D-01/D-02); Foxx is deprecated.**
```
Renumber or keep as a struck-through historical entry per team convention — RESEARCH.md and CONTEXT.md do not specify which; follow whatever the existing ROADMAP.md does elsewhere for retired criteria (grep for prior retirement precedent before deciding).

---

### `.planning/REQUIREMENTS.md` (documentation) — MODIFY

**Analog:** same file, lines 35-38 (requirement bullets) and 110-113 (status table).
```diff
-- [ ] **REQ-foxx-parity** (PRD §3.7): Hybrid-schema parity with legacy Foxx...
++- [x] **REQ-foxx-parity** (PRD §3.7): **RETIRED** via ADR-0003 (Appendix B.3) — Foxx is deprecated; no v1.0 acceptance gate. See §13.4 amendment.
```
```diff
-| REQ-foxx-parity | Phase 4 | Pending |
+| REQ-foxx-parity | Phase 4 | Retired |
```

## Shared Patterns

### Docker-gated boot/skip
**Source:** `tests/integration/conftest.py` (whole file, 159 lines) — `ensure_test_database()`, `integration_enabled()`, `arangodb_reachable()`, `try_boot_arangodb_via_compose()`.
**Apply to:** `test_aoe_roundtrip.py`, `test_sparqlwrapper_smoke.py`, `test_ontology_playground_roundtrip.py`. Import these functions directly rather than re-deriving the private copies still living in `test_execute_endpoint.py` (that file predates the shared `conftest.py` extraction and hasn't been migrated — new Phase-4 files should use the shared module).
```python
from tests.integration.conftest import (
    DEFAULT_ARANGO_URL, DEFAULT_ARANGO_DB, DEFAULT_ARANGO_USER, DEFAULT_ARANGO_PASSWORD,
    ensure_test_database, integration_enabled, arangodb_reachable, try_boot_arangodb_via_compose,
)
```

### `_FakeArangoClient` / `_FakeDb` / `_FakeCursor` test double
**Source:** `tests/test_service_sparql_routes.py` lines 96-239.
**Apply to:** `tests/perf/conftest.py`, `tests/perf/test_execute_overhead.py`, `tests/perf/test_translate_latency.py` — this is the ONLY sanctioned way to make the `/execute` CI-gated perf row genuinely dependency-free (Pitfall 2).

### `rdflib.Graph.isomorphic()` blank-node-safe equality
**Source:** verified this session (RESEARCH.md Pattern 1); no prior in-repo call site (only `graph.serialize`/`graph.parse` exist today) — this is genuinely new usage, not an extension of an existing helper.
**Apply to:** `test_aoe_roundtrip.py`, `test_ontology_playground_roundtrip.py`.

### Vendored-fixture provenance (`NOTICE.md`)
**Source:** `tests/nl2sparql/eval/vendored/ck25/NOTICE.md` and `tests/nl2sparql/eval/vendored/qald9plus/NOTICE.md`.
**Apply to:** `tests/fixtures/cosmic_coffee.rdf`'s companion notice file.

### ADR redirect-stub + PRD Appendix B body
**Source:** `docs/architecture/decisions/0001-named-graphs-per-document.md` (stub) + `docs/architecture/PRD.md` `### B.2` (body, lines 3606-3684).
**Apply to:** `docs/architecture/decisions/0003-foxx-parity-retired.md` + new `### B.3` in PRD.md.

### Error envelope `{"error": ..., "code": ...}`
**Source:** `arango_sparql/service/routes/mapping.py` lines 251-293 (`OwlBombError`/`OwlParseError` → `HTTPException(422, {"error": _sanitize_error(str(exc)), "code": exc.code})`).
**Apply to:** any new RDF/XML/JSON-LD/N-Triples parse-error branch added to `mapping.py` — do not invent a new error shape for the new formats.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `docs/howto/index.md`, `protege.md`, `yasgui.md`, `sparqlwrapper.md`, `ontology-playground.md`, `arq.md` | documentation | n/a | `docs/howto/` does not exist yet (verified this session — empty `ls`); no prior recipe-doc convention in this repo to copy structurally. Planner should draft these from PRD §11.2-§11.4 prose plus the `rsparql`/SPARQLWrapper invocations already verified in RESEARCH.md's Code Examples section, choosing a simple "Prerequisites / Connect / SELECT / ASK / Service Description / Transcript" template. |
| `docs/architecture/decisions/0003-foxx-parity-retired.md` **content** (as opposed to its stub shape, which does have an analog) | documentation | n/a | The ADR *stub* mirrors `0001-*.md` exactly; the ADR *body* (in PRD Appendix B.3) is new prose specific to this decision — RESEARCH.md's "State of the Art" and CONTEXT.md's D-01 rationale are the source material, not a code analog. |

## Metadata

**Analog search scope:** `tests/integration/`, `tests/test_service_sparql_routes.py`, `tests/cross/`, `tests/nl2sparql/eval/` (incl. `vendored/`), `tests/perf/` (does not exist yet), `arango_sparql/translate/owl.py`, `arango_sparql/service/routes/{mapping,schema,sparql}.py`, `arango_sparql/schema/cache.py`, `docs/architecture/decisions/`, `docs/architecture/PRD.md` (§3.7, §9.4, §11, §13.1, §13.4, Appendix B), `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `pyproject.toml`
**Files scanned:** ~20 read/grepped directly this session (see file:line citations above)
**Pattern extraction date:** 2026-07-27
