"""Report-only p95 latency row for ``GET /sparql`` — PRD §9.4 (D-09).

One of the 8 Docker/LLM/noisy §9.4 rows that measure a metric and
append it to the checked-in ``tests/perf/LATENCY_REPORT.md`` but
**never gate CI** (D-09) — unlike the three in-process rows in
``test_translate_latency.py``/``test_execute_overhead.py`` (D-08),
this row genuinely needs a live ArangoDB (the W3C protocol path reads
real collection data), so it is gated behind ``RUN_INTEGRATION=1``
and a real ``docker-compose`` ArangoDB exactly like every file under
``tests/integration/`` (boot/skip helpers imported, not re-copied,
from :mod:`tests.integration.conftest` per that module's own
docstring).

Schema activation mirrors ``tests/integration/test_aoe_roundtrip.py``
(RESEARCH.md Pattern 2): ``/mapping/*`` is stateless, so the seeded
collection's mapping is pushed directly into the process-wide
``SchemaCache`` rather than relying on heuristic/analyzer
auto-detection.

PRD §9.4 row: **`/sparql` GET (W3C protocol, JSON results, 1k-row
payload)** — target p95 ≤ 150ms, Report-only tier.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import (
    DEFAULT_ARANGO_DB,
    DEFAULT_ARANGO_PASSWORD,
    DEFAULT_ARANGO_URL,
    DEFAULT_ARANGO_USER,
    arangodb_reachable,
    ensure_test_database,
    integration_enabled,
    try_boot_arangodb_via_compose,
)
from tests.perf.conftest import append_report, p95

pytestmark = pytest.mark.perf

_TEST_COLLECTION = "PerfSparqlProtocolPerson"
_ROW_COUNT = 1000  # PRD §9.4's "1k-row payload"
_N_ITER = 15
_WARMUP = 3
_BUDGET_MS = 150.0

# Distinct namespace/collection from every other integration/perf
# fixture so seeded data + the process-wide SchemaCache entry never
# collide across sibling files sharing one RUN_INTEGRATION=1 session.
_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/perf-sparql#> .

:PerfSparqlProtocolPerson a owl:Class ;
    phys:collectionName "PerfSparqlProtocolPerson" .

:name a owl:DatatypeProperty ;
    rdfs:domain :PerfSparqlProtocolPerson ;
    rdfs:range  xsd:string .
"""

_SELECT_QUERY = (
    "PREFIX : <http://example.org/perf-sparql#> "
    "SELECT ?s ?n WHERE { ?s a :PerfSparqlProtocolPerson ; :name ?n }"
)


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped Docker gate, mirroring every ``tests/integration/*``
    file's fixture of the same name."""

    if not integration_enabled():
        pytest.skip("set RUN_INTEGRATION=1 to enable the Docker-gated perf report rows")
    if not arangodb_reachable():
        if not try_boot_arangodb_via_compose():
            pytest.skip(f"ArangoDB at {DEFAULT_ARANGO_URL} is unreachable and could not be booted")
    ensure_test_database()
    yield


@pytest.fixture(scope="module")
def _seeded_collection(_live_arango: None) -> Iterator[list[dict]]:
    """Drop-and-recreate a ``PerfSparqlProtocolPerson`` collection
    seeded with ``_ROW_COUNT`` rows — the "1k-row payload" PRD §9.4
    calls for on this row.
    """

    from arango import ArangoClient

    client = ArangoClient(hosts=DEFAULT_ARANGO_URL)
    db = client.db(DEFAULT_ARANGO_DB, username=DEFAULT_ARANGO_USER, password=DEFAULT_ARANGO_PASSWORD)

    if db.has_collection(_TEST_COLLECTION):
        db.delete_collection(_TEST_COLLECTION)
    coll = db.create_collection(_TEST_COLLECTION)

    docs = [{"_uri": f"http://example.org/perf-sparql#p{i}", "name": f"Person{i}"} for i in range(_ROW_COUNT)]
    coll.insert_many(docs)

    try:
        yield docs
    finally:
        try:
            db.delete_collection(_TEST_COLLECTION)
        except Exception:
            # Best-effort teardown — a failed delete shouldn't mask a
            # real test failure upstream.
            pass
        client.close()


def _connect_session(client: TestClient) -> str:
    resp = client.post(
        "/connect",
        json={
            "url": DEFAULT_ARANGO_URL,
            "database": DEFAULT_ARANGO_DB,
            "username": DEFAULT_ARANGO_USER,
            "password": DEFAULT_ARANGO_PASSWORD,
        },
    )
    assert resp.status_code == 200, f"connect failed: {resp.status_code} {resp.text}"
    payload = resp.json()
    assert payload["token"]
    return payload["token"]


def test_sparql_get_p95(monkeypatch: pytest.MonkeyPatch, _seeded_collection: list[dict]) -> None:
    """Report-only p95 for ``GET /sparql?query=...`` against the
    seeded 1k-row collection — never asserts against the §9.4 budget
    (D-09), only appends the measured number to ``LATENCY_REPORT.md``.
    """

    import arango_sparql.service as svc
    from arango_sparql.service import app
    from arango_sparql.service.routes.schema import _resolve_schema_cache
    from arango_sparql.service.security import _TokenBucket
    from arango_sparql.translate.owl import turtle_to_mapping

    # A high-capacity bucket keeps the loop deterministic regardless
    # of the default COMPUTE_RATE_LIMIT_PER_MINUTE (established
    # pattern: tests/test_service_nl_routes.py's _reset_rate_limits
    # fixture, reused verbatim by test_translate_latency.py Plan 06).
    monkeypatch.setattr(svc, "_compute_bucket", _TokenBucket(10_000))

    client = TestClient(app)
    token = _connect_session(client)

    # /mapping/import-owl is stateless (RESEARCH.md Pattern 2) — push
    # the mapping straight into the process-wide SchemaCache so
    # GET /sparql resolves it deterministically rather than depending
    # on heuristic/analyzer auto-detection.
    bundle = turtle_to_mapping(_ONTOLOGY_TTL)
    _resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)

    query_string = urllib.parse.urlencode({"query": _SELECT_QUERY})
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/sparql-results+json",
    }

    samples: list[float] = []
    for _ in range(_N_ITER):
        t0 = time.perf_counter()
        resp = client.get(f"/sparql?{query_string}", headers=headers)
        samples.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert len(payload["results"]["bindings"]) == len(_seeded_collection)

    measured = p95(samples[_WARMUP:])
    append_report("sparql_get_p95_ms", measured, _BUDGET_MS)
