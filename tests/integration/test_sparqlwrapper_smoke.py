"""SPARQLWrapper smoke test — REQ-thirdparty-tool-compat (D-06).

Drives our own ``/sparql`` W3C SPARQL 1.1 Protocol endpoint with a
**real** ``SPARQLWrapper`` client (a genuine ``urllib``-based HTTP
client — PRD §11.1 names it as the automated compat target) over a
**real bound TCP socket**. FastAPI's in-process ASGI test transport
never opens a socket, so it cannot be ``SPARQLWrapper``'s target
(04-RESEARCH.md Pattern 4 / Anti-Pattern); instead a background
``uvicorn.Server`` thread binds ``127.0.0.1:0`` (an ephemeral port)
and the test resolves the actual bound port before firing queries.
Every HTTP call in this file — ``/connect``, the Service Description
fetch, and the SPARQLWrapper SELECT/ASK queries — travels over that
same real socket.

Coverage (D-06):

* ``SELECT`` — bindings for the seeded rows.
* ``ASK`` — a ``true`` and a ``false`` variant, asserting the JSON
  result carries a ``boolean`` key of type ``bool`` (Assumption A2 in
  04-RESEARCH.md).
* Service Description — an unauthenticated ``GET /sparql`` (no
  ``query`` param) returns a ``text/turtle`` SPARQL Service
  Description document.

Schema activation mirrors ``tests/integration/test_aoe_roundtrip.py``:
``/mapping/import-owl``/``export-owl`` are stateless, so
``SchemaCache.put()`` (RESEARCH.md Pattern 2) deterministically makes
the seeded collection queryable via ``/sparql`` rather than depending
on heuristic/analyzer auto-detection to rediscover it. The cache
injection itself runs in-process (it's a plain Python call, not an
HTTP request) since the background server shares this same process
and its module-global schema cache.

Gated behind the ``integration`` marker and ``RUN_INTEGRATION=1``,
mirroring every other file in this directory. Run explicitly with::

    RUN_INTEGRATION=1 .venv/bin/pytest -q -m integration tests/integration/test_sparqlwrapper_smoke.py
"""

from __future__ import annotations

import json as _json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

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

pytestmark = pytest.mark.integration

_TEST_COLLECTION = "SparqlwrapperPerson"

# Distinct collection name + namespace from both
# ``test_execute_endpoint.py``'s ``Person`` and
# ``test_aoe_roundtrip.py``'s ``AoePerson`` fixtures so seeded data
# and the process-wide ``SchemaCache`` entry never collide across
# sibling integration files sharing one ``RUN_INTEGRATION=1`` session.
_SPARQLWRAPPER_PERSON_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/sw#> .

:SparqlwrapperPerson a owl:Class ;
    phys:collectionName "SparqlwrapperPerson" .

:name a owl:DatatypeProperty ;
    rdfs:domain :SparqlwrapperPerson ;
    rdfs:range  xsd:string .

:age a owl:DatatypeProperty ;
    rdfs:domain :SparqlwrapperPerson ;
    rdfs:range  xsd:integer .
"""


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped guard: skip every test in this file unless we can
    talk to ArangoDB, mirroring ``test_aoe_roundtrip.py``'s fixture of
    the same name.
    """

    if not integration_enabled():
        pytest.skip("set RUN_INTEGRATION=1 to enable integration tests")
    if not arangodb_reachable():
        if not try_boot_arangodb_via_compose():
            pytest.skip(f"ArangoDB at {DEFAULT_ARANGO_URL} is unreachable and could not be booted")
    ensure_test_database()
    yield


@pytest.fixture(scope="module")
def _seeded_collection(_live_arango: None) -> Iterator[list[dict]]:
    """Drop-and-recreate a small ``SparqlwrapperPerson`` collection
    seeded with three rows so ``SELECT`` returns a non-empty binding
    set and ``ASK`` has both a ``true`` and a ``false`` case to prove.
    """

    from arango import ArangoClient

    client = ArangoClient(hosts=DEFAULT_ARANGO_URL)
    db = client.db(DEFAULT_ARANGO_DB, username=DEFAULT_ARANGO_USER, password=DEFAULT_ARANGO_PASSWORD)

    if db.has_collection(_TEST_COLLECTION):
        db.delete_collection(_TEST_COLLECTION)
    coll = db.create_collection(_TEST_COLLECTION)

    docs = [
        {"_uri": "http://example.org/sw#frank", "name": "Frank", "age": 29},
        {"_uri": "http://example.org/sw#grace", "name": "Grace", "age": 38},
        {"_uri": "http://example.org/sw#heidi", "name": "Heidi", "age": 45},
    ]
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


@pytest.fixture(scope="module")
def _live_server(_seeded_collection: list[dict]) -> Iterator[int]:
    """Bind a real ``uvicorn.Server`` to ``127.0.0.1:0`` (an ephemeral
    port) in a background daemon thread — the only way to give a real
    HTTP client (``SPARQLWrapper``) something to connect to, since an
    in-process ASGI transport never opens a socket (04-RESEARCH.md
    Pattern 4).

    Waits on ``server.started`` and then polls the bound port with a
    real HTTP GET until it actually answers, closing the startup-race
    window the plan calls out (a ``started`` flag can flip slightly
    before the listening socket is fully ready to accept traffic).
    """

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

    # Readiness wait — poll a real HTTP request against the bound
    # socket until it succeeds, so the very first real client request
    # doesn't race the listener's accept-loop startup.
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


def _connect_session(port: int) -> str:
    """POST a real ``/connect`` request over the bound socket and
    return the session token."""

    body = _json.dumps(
        {
            "url": DEFAULT_ARANGO_URL,
            "database": DEFAULT_ARANGO_DB,
            "username": DEFAULT_ARANGO_USER,
            "password": DEFAULT_ARANGO_PASSWORD,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/connect",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5.0) as resp:
        assert resp.status == 200
        payload = _json.loads(resp.read().decode("utf-8"))
    assert payload["token"]
    return payload["token"]


@pytest.fixture(scope="module")
def _session_token(_live_server: int) -> str:
    """A connected session token (resolved over the real bound socket)
    with the seeded collection's bundle deterministically activated in
    the process-wide ``SchemaCache`` (RESEARCH.md Pattern 2 —
    ``/mapping/*`` routes are stateless, so there is no automatic
    wiring from an import to ``/sparql`` querying it; direct cache
    injection is the deterministic path). The injection call itself is
    a plain in-process Python call — the background server shares this
    process's module-global schema cache.
    """

    from arango_sparql.service.routes.schema import _resolve_schema_cache
    from arango_sparql.translate.owl import turtle_to_mapping

    token = _connect_session(_live_server)
    bundle = turtle_to_mapping(_SPARQLWRAPPER_PERSON_ONTOLOGY_TTL)
    _resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)
    return token


# ---------------------------------------------------------------------------
# Task 1: SPARQLWrapper smoke — SELECT + ASK + Service Description
# ---------------------------------------------------------------------------


def _make_wrapper(port: int, token: str) -> Any:
    """Construct a ``SPARQLWrapper`` client targeting the real bound
    server, authenticated via the session token as a bearer header
    (mirroring ``_resolve_protocol_session``'s ``Authorization: Bearer``
    lookup path).
    """

    from SPARQLWrapper import JSON, POST, SPARQLWrapper

    sparql = SPARQLWrapper(f"http://127.0.0.1:{port}/sparql")
    sparql.setMethod(POST)
    sparql.setReturnFormat(JSON)
    sparql.addCustomHttpHeader("Authorization", f"Bearer {token}")
    return sparql


def test_sparqlwrapper_select_returns_seeded_bindings(
    _live_server: int,
    _session_token: str,
    _seeded_collection: list[dict],
) -> None:
    """A real ``SPARQLWrapper`` SELECT against our bound ``/sparql``
    returns a well-formed ``results.bindings`` list matching the
    seeded rows."""

    sparql = _make_wrapper(_live_server, _session_token)
    sparql.setQuery(
        "PREFIX : <http://example.org/sw#> "
        "SELECT ?s ?n WHERE { ?s a :SparqlwrapperPerson ; :name ?n }"
    )
    results = sparql.query().convert()

    assert "results" in results
    assert "bindings" in results["results"]
    bindings = results["results"]["bindings"]
    assert len(bindings) == len(_seeded_collection), bindings
    seen_names = {row["n"]["value"] for row in bindings}
    assert seen_names == {row["name"] for row in _seeded_collection}


def test_sparqlwrapper_ask_returns_boolean(
    _live_server: int,
    _session_token: str,
) -> None:
    """A real ``SPARQLWrapper`` ASK against our bound ``/sparql``
    returns a JSON result whose ``boolean`` key is a real Python
    ``bool`` (Assumption A2), both for a matching row (``True``) and a
    made-up name (``False``)."""

    sparql = _make_wrapper(_live_server, _session_token)

    sparql.setQuery(
        'PREFIX : <http://example.org/sw#> ASK { ?s a :SparqlwrapperPerson ; :name "Frank" }'
    )
    ask_true = sparql.query().convert()
    assert isinstance(ask_true.get("boolean"), bool)
    assert ask_true["boolean"] is True

    sparql.setQuery(
        'PREFIX : <http://example.org/sw#> ASK { ?s a :SparqlwrapperPerson ; :name "NoSuchPerson" }'
    )
    ask_false = sparql.query().convert()
    assert isinstance(ask_false.get("boolean"), bool)
    assert ask_false["boolean"] is False


def test_service_description_over_real_socket(_live_server: int) -> None:
    """An unauthenticated ``GET /sparql`` (no ``query`` param) against
    the real bound socket returns a ``text/turtle`` SPARQL 1.1 Service
    Description document — proving a plain HTTP client can discover
    the endpoint's capabilities over the wire, per D-06/PRD §5.2."""

    with urllib.request.urlopen(f"http://127.0.0.1:{_live_server}/sparql", timeout=5.0) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert content_type.startswith("text/turtle")
        body = resp.read().decode("utf-8")
    assert "sparql-service-description" in body
