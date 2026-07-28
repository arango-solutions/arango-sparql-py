"""Ontology Playground RDF/XML roundtrip — REQ-thirdparty-tool-compat (D-06).

File-based fidelity test for the Microsoft Ontology Playground
integration path (PRD §11.3): the vendored ``cosmic_coffee.rdf``
fixture (RDF/XML, MIT, 349 triples — see
``tests/fixtures/cosmic_coffee.NOTICE.md``) round-trips through
``POST /mapping/import-owl`` (``Content-Type: application/rdf+xml``)
-> ``POST /mapping/export-owl`` (``Accept: application/rdf+xml``) with
blank-node-safe triple-bag equality (``rdflib.Graph.isomorphic()``,
04-RESEARCH.md Pattern 1).

This is **pure OWL fidelity** — no ``/sparql`` query, no
``phys:collectionName`` annotations required. ``cosmic_coffee.rdf``
is the Ontology Playground *catalogue* fixture, not a
``phys:``-annotated physical-mapping fixture; it must never be reused
for the AOE own-half contract test (``tests/integration/
test_aoe_roundtrip.py``), which needs a queryable schema instead
(04-RESEARCH.md Pitfall 3).

Docker-gated (the ``/mapping`` routes require an authenticated
session, which in turn needs a live ``/connect`` target) via the
shared ``tests/integration/conftest.py`` boot/skip helpers. Run
explicitly with::

    RUN_INTEGRATION=1 .venv/bin/pytest -q -m integration tests/integration/test_ontology_playground_roundtrip.py
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

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

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "cosmic_coffee.rdf"


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped guard: skip every test in this file unless we can
    talk to ArangoDB, mirroring the other Phase-4 integration files.
    A live database isn't strictly needed for the OWL roundtrip
    itself (it's file-based), but ``/mapping/import-owl`` and
    ``/mapping/export-owl`` both require an authenticated session,
    which in turn requires a real ``/connect`` target.
    """

    if not integration_enabled():
        pytest.skip("set RUN_INTEGRATION=1 to enable integration tests")
    if not arangodb_reachable():
        if not try_boot_arangodb_via_compose():
            pytest.skip(f"ArangoDB at {DEFAULT_ARANGO_URL} is unreachable and could not be booted")
    ensure_test_database()
    yield


def _connect_session(client) -> str:
    """POST ``/connect`` and return the session token. Mirrors
    ``test_aoe_roundtrip.py``'s helper of the same name."""

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


def test_cosmic_coffee_rdfxml_roundtrip_is_isomorphic(_live_arango: None) -> None:
    """``import-owl`` (``application/rdf+xml``) -> ``export-owl``
    (``Accept: application/rdf+xml``) round-trips ``cosmic_coffee.rdf``
    with blank-node-safe triple-bag equality (D-06)."""

    from fastapi.testclient import TestClient

    from arango_sparql.service import app

    fixture_bytes = _FIXTURE_PATH.read_bytes()

    client = TestClient(app)
    token = _connect_session(client)
    headers = {"Authorization": f"Bearer {token}"}

    import_resp = client.post(
        "/mapping/import-owl",
        content=fixture_bytes,
        headers={**headers, "Content-Type": "application/rdf+xml"},
    )
    assert import_resp.status_code == 200, import_resp.text
    imported = import_resp.json()
    assert imported["accepted"] is True
    assert imported["triple_count"] > 0
    mapping_wire = imported["mapping"]

    export_resp = client.post(
        "/mapping/export-owl",
        json={"mapping": mapping_wire},
        headers={**headers, "Accept": "application/rdf+xml"},
    )
    assert export_resp.status_code == 200, export_resp.text
    assert export_resp.headers["content-type"].startswith("application/rdf+xml")
    exported_rdfxml = export_resp.text

    g1 = Graph()
    g1.parse(data=fixture_bytes, format="xml")
    g2 = Graph()
    g2.parse(data=exported_rdfxml, format="xml")
    assert g1.isomorphic(g2), "re-exported cosmic_coffee.rdf is not isomorphic to the original fixture"


def test_cosmic_coffee_rdfxml_roundtrip_preserves_triple_count(_live_arango: None) -> None:
    """The ``x-triple-count`` header on the export response matches
    the original fixture's triple count — a cheap, independent sanity
    check alongside the isomorphism assertion above (no lossy
    re-serialisation of entities/relationships along the way)."""

    from fastapi.testclient import TestClient

    from arango_sparql.service import app

    fixture_bytes = _FIXTURE_PATH.read_bytes()
    original_graph = Graph()
    original_graph.parse(data=fixture_bytes, format="xml")
    original_triple_count = len(original_graph)

    client = TestClient(app)
    token = _connect_session(client)
    headers = {"Authorization": f"Bearer {token}"}

    import_resp = client.post(
        "/mapping/import-owl",
        content=fixture_bytes,
        headers={**headers, "Content-Type": "application/rdf+xml"},
    )
    assert import_resp.status_code == 200, import_resp.text
    mapping_wire = import_resp.json()["mapping"]

    export_resp = client.post(
        "/mapping/export-owl",
        json={"mapping": mapping_wire},
        headers={**headers, "Accept": "application/rdf+xml"},
    )
    assert export_resp.status_code == 200, export_resp.text
    assert int(export_resp.headers["x-triple-count"]) == original_triple_count
