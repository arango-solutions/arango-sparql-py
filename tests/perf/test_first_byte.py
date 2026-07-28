"""Report-only time-to-first-byte row for ``GET /sparql`` — PRD §9.4
(D-09).

PRD §9.4 row: **Result-streaming chunk size** (W3C protocol, JSON) —
target ``first byte <= 200ms``, Report-only tier.

FastAPI's in-process ASGI ``TestClient`` transport never opens a real
socket, so it cannot observe genuine TCP/HTTP first-byte timing (every
other row in this suite that only needs *request/response* latency
uses ``TestClient`` for exactly that reason — it's cheaper and the
distinction doesn't matter there). This row is different: "first
byte" is only a meaningful, distinct measurement over a **real bound
socket**, so this file reuses
``tests/integration/test_sparqlwrapper_smoke.py``'s verified
live-``uvicorn.Server``-in-a-daemon-thread fixture (04-RESEARCH.md
Pattern 4) rather than ``TestClient``.

``urllib.request.urlopen(...)`` returns as soon as the response status
line + headers have arrived — before the body is (necessarily) fully
read — so timing from just-before-``urlopen`` to just-after is the
standard proxy for time-to-first-byte a plain stdlib HTTP client can
observe without a raw-socket implementation.

Gated behind ``RUN_INTEGRATION=1`` + a real ``docker-compose``
ArangoDB, mirroring every other Docker-dependent report row.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

import pytest

from tests.perf.conftest import (
    DEFAULT_ARANGO_DB,
    arango_seeded_collection,
    append_report,
    connect_session_over_socket_or_skip,
    live_arango_or_skip,
    p95,
)

pytestmark = pytest.mark.perf

_TEST_COLLECTION = "PerfFirstBytePerson"
_ROW_COUNT = 500
_N_ITER = 10
_WARMUP = 2
_BUDGET_MS = 200.0

_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/perf-firstbyte#> .

:PerfFirstBytePerson a owl:Class ;
    phys:collectionName "PerfFirstBytePerson" .

:name a owl:DatatypeProperty ;
    rdfs:domain :PerfFirstBytePerson ;
    rdfs:range  xsd:string .
"""

_SELECT_QUERY = (
    "PREFIX : <http://example.org/perf-firstbyte#> "
    "SELECT ?s ?n WHERE { ?s a :PerfFirstBytePerson ; :name ?n }"
)


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped Docker + connect/auth gate — see
    ``tests/perf/conftest.py``'s :func:`live_arango_or_skip` (never
    ERRORs on a connect/auth failure; skip-gates instead)."""

    live_arango_or_skip()
    yield


@pytest.fixture(scope="module")
def _seeded_collection(_live_arango: None) -> Iterator[list[dict]]:
    """Drop-and-recreate a ``PerfFirstBytePerson`` collection seeded
    with ``_ROW_COUNT`` rows -- large enough that a real TCP transfer
    has observable duration beyond header arrival."""

    docs = [
        {"_uri": f"http://example.org/perf-firstbyte#p{i}", "name": f"Person{i}"} for i in range(_ROW_COUNT)
    ]
    with arango_seeded_collection(_TEST_COLLECTION, docs) as seeded:
        yield seeded


@pytest.fixture(scope="module")
def _live_server(_seeded_collection: list[dict]) -> Iterator[int]:
    """Bind a real ``uvicorn.Server`` to ``127.0.0.1:0`` in a
    background daemon thread -- verbatim pattern from
    ``tests/integration/test_sparqlwrapper_smoke.py`` (04-RESEARCH.md
    Pattern 4), reused here because first-byte timing is only
    meaningful over a real socket."""

    import uvicorn

    from arango_sparql.service import app

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10.0
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5.0)
        pytest.fail("uvicorn server did not report started within 10s")

    _host, port = server.servers[0].sockets[0].getsockname()[:2]

    ready = False
    ready_deadline = time.time() + 10.0
    while time.time() < ready_deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/sparql", timeout=1.0) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.1)
    if not ready:
        server.should_exit = True
        thread.join(timeout=5.0)
        pytest.fail(f"uvicorn server on port {port} never answered a request within 10s")

    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


def test_first_byte_p95(_live_server: int) -> None:
    """Report-only time-to-first-byte p95 for ``GET /sparql`` over the
    real bound socket. Never asserts against the §9.4 budget (D-09) —
    only appends the measured number to ``LATENCY_REPORT.md``.
    """

    from arango_sparql.service.routes.schema import _resolve_schema_cache
    from arango_sparql.translate.owl import turtle_to_mapping

    token = connect_session_over_socket_or_skip(_live_server)
    # /mapping/import-owl is stateless (RESEARCH.md Pattern 2) -- push
    # the mapping straight into the process-wide SchemaCache; the
    # background server shares this process's module-global cache.
    bundle = turtle_to_mapping(_ONTOLOGY_TTL)
    _resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)

    query_string = urllib.parse.urlencode({"query": _SELECT_QUERY})
    url = f"http://127.0.0.1:{_live_server}/sparql?{query_string}"

    samples: list[float] = []
    for _ in range(_N_ITER):
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/sparql-results+json",
            },
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            # Headers have arrived -- this is the first-byte proxy.
            ttfb_ms = (time.perf_counter() - t0) * 1000
            assert resp.status == 200
            resp.read()  # drain the body so the connection can be reused
        samples.append(ttfb_ms)

    measured = p95(samples[_WARMUP:])
    append_report("first_byte_p95_ms", measured, _BUDGET_MS)
