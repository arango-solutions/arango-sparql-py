"""AOE (``arango-ontoextract``) own-half contract test — REQ-ontoextract-integration.

Tests **our** half of the AOE contract only (D-03/D-04 in
``.planning/phases/04-interoperability-performance-verification/04-CONTEXT.md``):
a ``phys:``-annotated OWL ontology round-trips
``POST /mapping/import-owl`` -> ``POST /mapping/export-owl`` with
triple-bag equality (modulo blank-node renaming, via
``rdflib.Graph.isomorphic()``) for both Turtle and RDF/XML, then the
imported mapping is made queryable via
``SchemaCache.put()`` so an ``ASK``/``SELECT`` through ``POST /sparql``
resolves against a live docker-compose ArangoDB (host 8532, DB
``sparql-to-aql``).

NO external ``arango-ontoextract`` service is cloned or run here —
AOE's own integration is documented as "one env var" (PRD §12.2); the
substance worth proving is our endpoints' OWL fidelity plus
queryability, which is exactly what this module exercises.

Gated behind the ``integration`` marker (declared in ``pyproject.toml``)
and the ``RUN_INTEGRATION=1`` env var, mirroring
``tests/integration/test_execute_endpoint.py``. Run explicitly with::

    RUN_INTEGRATION=1 .venv/bin/pytest -q -m integration tests/integration/test_aoe_roundtrip.py

Boot/skip helpers are imported (not re-copied) from
``tests.integration.conftest`` per that module's own docstring.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from rdflib import Graph

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

_TEST_COLLECTION = "AoePerson"

# Extends the proven ``_PERSON_ONTOLOGY_TTL`` fixture shape from
# ``tests/integration/test_execute_endpoint.py`` (Pitfall 3 in
# 04-RESEARCH.md: do NOT reuse ``cosmic_coffee.rdf`` here — it carries
# no ``phys:collectionName`` annotations and cannot resolve at
# ``/sparql``). A distinct collection name/namespace (``AoePerson``,
# ``example.org/aoe#``) keeps this file's seeded data from colliding
# with ``test_execute_endpoint.py``'s own ``Person`` collection when
# both run in the same ``RUN_INTEGRATION=1`` session.
_AOE_PERSON_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/aoe#> .

:AoePerson a owl:Class ;
    phys:collectionName "AoePerson" .

:name a owl:DatatypeProperty ;
    rdfs:domain :AoePerson ;
    rdfs:range  xsd:string .

:age a owl:DatatypeProperty ;
    rdfs:domain :AoePerson ;
    rdfs:range  xsd:integer .
"""


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped guard: skip every test in this file unless we can
    talk to ArangoDB, mirroring ``test_execute_endpoint.py``'s fixture
    of the same name but built on the shared ``conftest.py`` helpers.
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
    """Drop-and-recreate a small ``AoePerson`` collection seeded with
    two rows — one name each so an ``ASK`` on a real name is ``true``
    and an ``ASK`` on a made-up name is ``false``, and a ``SELECT``
    returns a non-empty, well-formed binding set (Task 2 / T-04-07).
    """

    from arango import ArangoClient

    client = ArangoClient(hosts=DEFAULT_ARANGO_URL)
    db = client.db(DEFAULT_ARANGO_DB, username=DEFAULT_ARANGO_USER, password=DEFAULT_ARANGO_PASSWORD)

    if db.has_collection(_TEST_COLLECTION):
        db.delete_collection(_TEST_COLLECTION)
    coll = db.create_collection(_TEST_COLLECTION)

    docs = [
        {"_uri": "http://example.org/aoe#dana", "name": "Dana", "age": 33},
        {"_uri": "http://example.org/aoe#eli", "name": "Eli", "age": 51},
    ]
    coll.insert_many(docs)

    try:
        yield docs
    finally:
        try:
            db.delete_collection(_TEST_COLLECTION)
        except Exception:
            # Best-effort teardown — a failed delete shouldn't mask a
            # real test failure upstream (T-04-07 isolation).
            pass
        client.close()


def _connect_session(client: Any) -> str:
    """POST ``/connect`` and return the session token. Mirrors
    ``test_execute_endpoint.py``'s helper of the same name.
    """

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


def _auth_headers(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _import_owl(client: Any, token: str, content: str, content_type: str) -> dict:
    """POST ``/mapping/import-owl`` with *content* in *content_type*
    and return the parsed JSON response body (the ``OwlImportResponse``
    shape, carrying the wire-dict ``mapping``).
    """

    resp = client.post(
        "/mapping/import-owl",
        content=content.encode("utf-8"),
        headers=_auth_headers(token, **{"Content-Type": content_type}),
    )
    assert resp.status_code == 200, f"import-owl failed: {resp.status_code} {resp.text}"
    return resp.json()


def _export_owl(client: Any, token: str, mapping: dict, accept: str) -> str:
    """POST ``/mapping/export-owl`` with *mapping* and return the raw
    exported text in the negotiated *accept* format.
    """

    resp = client.post(
        "/mapping/export-owl",
        json={"mapping": mapping},
        headers=_auth_headers(token, Accept=accept),
    )
    assert resp.status_code == 200, f"export-owl failed: {resp.status_code} {resp.text}"
    return resp.text


# ---------------------------------------------------------------------------
# Task 1: Turtle + RDF/XML export -> import triple-bag isomorphism
# ---------------------------------------------------------------------------


def test_aoe_roundtrip_turtle_isomorphic(_live_arango: None) -> None:
    """``import-owl`` (Turtle) -> ``export-owl`` (``Accept: text/turtle``)
    round-trips with triple-bag equality (``rdflib.Graph.isomorphic``,
    blank-node-safe per RESEARCH.md Pattern 1).
    """

    from fastapi.testclient import TestClient

    from arango_sparql.service import app

    client = TestClient(app)
    token = _connect_session(client)

    imported = _import_owl(client, token, _AOE_PERSON_ONTOLOGY_TTL, "text/turtle")
    exported_turtle = _export_owl(client, token, imported["mapping"], "text/turtle")

    g1 = Graph()
    g1.parse(data=_AOE_PERSON_ONTOLOGY_TTL, format="turtle")
    g2 = Graph()
    g2.parse(data=exported_turtle, format="turtle")
    assert g1.isomorphic(g2), "Turtle export-owl output is not isomorphic to the imported source"


def test_aoe_roundtrip_rdfxml_isomorphic(_live_arango: None) -> None:
    """The same contract driven entirely through RDF/XML on both the
    import ``Content-Type`` and the export ``Accept`` negotiation
    (D-04's RDF/XML row, unblocked by Plan 04-02's format-dispatch
    work).
    """

    from fastapi.testclient import TestClient

    from arango_sparql.service import app

    client = TestClient(app)
    token = _connect_session(client)

    # Serialise the canonical Turtle fixture to RDF/XML first so the
    # *import* side genuinely exercises the RDF/XML parse path (not
    # just the export side).
    source_graph = Graph()
    source_graph.parse(data=_AOE_PERSON_ONTOLOGY_TTL, format="turtle")
    source_rdfxml = source_graph.serialize(format="xml")

    imported = _import_owl(client, token, source_rdfxml, "application/rdf+xml")
    exported_rdfxml = _export_owl(client, token, imported["mapping"], "application/rdf+xml")

    g1 = Graph()
    g1.parse(data=source_rdfxml, format="xml")
    g2 = Graph()
    g2.parse(data=exported_rdfxml, format="xml")
    assert g1.isomorphic(g2), "RDF/XML export-owl output is not isomorphic to the imported source"


# ---------------------------------------------------------------------------
# Task 2: SchemaCache activation + ASK/SELECT via /sparql
# ---------------------------------------------------------------------------


def test_aoe_imported_mapping_is_queryable_via_sparql(_seeded_collection: list[dict]) -> None:
    """After ``SchemaCache.put()`` activation (RESEARCH.md Pattern 2 —
    ``/mapping/import-owl``/``/mapping/export-owl`` are stateless, so
    there is no automatic wiring from "I just imported this OWL" to
    "``/sparql`` now sees it"), the imported mapping resolves through
    ``/sparql``: ``ASK`` returns a boolean (both a ``true`` and a
    ``false`` variant), ``SELECT`` returns well-formed bindings for the
    seeded rows.
    """

    from fastapi.testclient import TestClient

    from arango_sparql.service import app
    from arango_sparql.service.routes.schema import _resolve_schema_cache
    from arango_sparql.translate.owl import turtle_to_mapping

    client = TestClient(app)
    token = _connect_session(client)

    # import-owl is stateless (operates on the request body only) —
    # deterministically activate the same bundle for /sparql via the
    # process-wide SchemaCache rather than relying on heuristic/
    # analyzer auto-detection to rediscover it from live collection
    # contents.
    bundle = turtle_to_mapping(_AOE_PERSON_ONTOLOGY_TTL)
    _resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)

    ask_true = 'PREFIX : <http://example.org/aoe#> ASK { ?s a :AoePerson ; :name "Dana" }'
    resp = client.post(
        "/sparql",
        headers=_auth_headers(token),
        data={"query": ask_true},
    )
    assert resp.status_code == 200, resp.text
    payload = json.loads(resp.text)
    assert isinstance(payload.get("boolean"), bool)
    assert payload["boolean"] is True

    ask_false = 'PREFIX : <http://example.org/aoe#> ASK { ?s a :AoePerson ; :name "NoSuchPerson" }'
    resp = client.post(
        "/sparql",
        headers=_auth_headers(token),
        data={"query": ask_false},
    )
    assert resp.status_code == 200, resp.text
    payload = json.loads(resp.text)
    assert isinstance(payload.get("boolean"), bool)
    assert payload["boolean"] is False

    select_query = "PREFIX : <http://example.org/aoe#> SELECT ?s ?n WHERE { ?s a :AoePerson ; :name ?n }"
    resp = client.post(
        "/sparql",
        headers=_auth_headers(token),
        data={"query": select_query},
    )
    assert resp.status_code == 200, resp.text
    payload = json.loads(resp.text)
    bindings = payload["results"]["bindings"]
    assert len(bindings) == len(_seeded_collection), bindings
    seen_names = {row["n"]["value"] for row in bindings}
    assert seen_names == {row["name"] for row in _seeded_collection}
