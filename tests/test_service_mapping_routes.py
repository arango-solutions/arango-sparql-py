"""End-to-end tests for the OWL import/export HTTP routes (PRD §6.4
rows 8 & 9).

Coverage goals:

* Auth model — both routes require a session.
* Happy path import — raw ``text/turtle`` body parses cleanly and
  returns a ``{accepted, mapping, triple_count}`` envelope.
* JSON envelope import — same surface, accepts
  ``{turtle, source_notes?}``.
* Happy path export — JSON envelope returns Turtle in body; the
  ``Accept: text/turtle`` content negotiation returns raw Turtle
  with the correct ``Content-Type``.
* OWL-bomb defences (PRD §8.6 T7):
  * Byte ceiling — request body > ``MAPPING_IMPORT_MAX_BYTES``
    returns 413 with ``E_OWL_TOO_LARGE``.
  * Triple cap — body that parses to > ``MAPPING_IMPORT_MAX_TRIPLES``
    returns 422 with ``E_OWL_TOO_LARGE``.
* Malformed input — non-Turtle body returns 422
  ``E_OWL_PARSE``; unrecognised JSON shape returns 422
  ``E_OWL_BAD_JSON``; non-UTF-8 body returns 422
  ``E_OWL_NOT_UTF8``; empty body returns 422
  ``E_OWL_EMPTY_BODY``.
* Round-trip — import → export → import yields the same entity /
  relationship surface.
* OpenAPI — both routes appear in the generated spec under
  ``/mapping/import-owl`` and ``/mapping/export-owl``.

The test file follows the same fake-arango / session fixture
pattern established in :mod:`tests.test_service_schema_routes`.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph

import arango_sparql.service as svc
from arango_sparql.service import _sessions, app

# ---------------------------------------------------------------------------
# Fake python-arango — minimal stub so /connect succeeds.
# ---------------------------------------------------------------------------


class _FakeAql:
    def execute(self, query: str, bind_vars: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return []


class _FakeDb:
    def __init__(self, name: str = "test_db") -> None:
        self.name = name
        self.aql = _FakeAql()

    def collections(self) -> list[dict[str, Any]]:
        return []

    def version(self) -> str:
        return "3.12.0"


class _FakeArangoClient:
    instances: list[_FakeArangoClient] = []

    def __init__(self, hosts: str = "") -> None:
        self.hosts = hosts
        self._dbs: dict[str, _FakeDb] = {}
        _FakeArangoClient.instances.append(self)

    def db(
        self,
        name: str,
        username: str | None = None,
        password: str | None = None,
    ) -> _FakeDb:
        if name not in self._dbs:
            self._dbs[name] = _FakeDb(name=name)
        return self._dbs[name]

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PG_TURTLE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://ex.org/> .

ex:Person a owl:Class ;
    phys:collectionName "Person" ;
    phys:mappingStyle "COLLECTION" .

ex:Org a owl:Class ;
    phys:collectionName "Org" ;
    phys:mappingStyle "COLLECTION" .

ex:knows a owl:ObjectProperty ;
    phys:edgeCollectionName "knows" ;
    phys:mappingStyle "DEDICATED_COLLECTION" ;
    rdfs:domain ex:Person ;
    rdfs:range  ex:Person .
"""


def _pg_rdfxml() -> str:
    g = Graph()
    g.parse(data=PG_TURTLE, format="turtle")
    return g.serialize(format="xml")


PG_RDFXML = _pg_rdfxml()

_XML_BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#">
  <owl:Class rdf:about="http://ex.org/Person">
    <rdf:comment>&lol2;</rdf:comment>
  </owl:Class>
</rdf:RDF>
"""


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch: pytest.MonkeyPatch):
    """Clear sessions and pin OWL-bomb env vars to their defaults
    so a leaked env var from another test cannot flap responses.
    """

    _sessions.clear()
    monkeypatch.delenv("MAPPING_IMPORT_MAX_BYTES", raising=False)
    monkeypatch.delenv("MAPPING_IMPORT_MAX_TRIPLES", raising=False)
    yield
    for s in list(_sessions.values()):
        try:
            s.client.close()
        except Exception:
            pass
    _sessions.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fake_arango(monkeypatch: pytest.MonkeyPatch):
    _FakeArangoClient.instances.clear()
    monkeypatch.setattr(svc, "ArangoClient", _FakeArangoClient)
    monkeypatch.setenv("ARANGO_SPARQL_CONNECT_ALLOWED_HOSTS", "localhost,127.0.0.1")
    return _FakeArangoClient


@pytest.fixture
def session_token(client: TestClient, fake_arango: type) -> str:
    resp = client.post(
        "/connect",
        json={
            "url": "http://localhost:8529",
            "database": "test_db",
            "username": "root",
            "password": "<test-stub-pw>",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_import_requires_session(client: TestClient) -> None:
    resp = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={"Content-Type": "text/turtle"},
    )
    assert resp.status_code == 401


def test_export_requires_session(client: TestClient) -> None:
    resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Happy path — import
# ---------------------------------------------------------------------------


def test_import_raw_turtle_body(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["triple_count"] > 0
    assert "mapping" in body
    pm = body["mapping"]["physicalMapping"]
    assert "Person" in pm["entities"]
    assert "knows" in pm["relationships"]
    assert pm["relationships"]["knows"]["fromEntity"] == "Person"


def test_import_json_envelope(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        json={"turtle": PG_TURTLE, "source_notes": "ui upload"},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["source"]["kind"] == "imported_owl"
    assert body["source"]["notes"] == "ui upload"


def test_import_response_includes_elapsed_ms(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        json={"turtle": PG_TURTLE},
        headers={"X-Arango-Session": session_token},
    )
    body = resp.json()
    assert "elapsed_ms" in body
    assert isinstance(body["elapsed_ms"], (int, float))
    assert body["elapsed_ms"] >= 0


def test_import_records_triple_count(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    body = resp.json()
    # The fixture parses to ~10–15 triples depending on how rdflib
    # collapses the predicate-object lists; the exact number is
    # implementation-defined but must be a positive integer.
    assert isinstance(body["triple_count"], int)
    assert body["triple_count"] >= 8


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


def test_import_empty_body_returns_422(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        content=b"",
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "E_OWL_EMPTY_BODY"


def test_import_malformed_turtle_returns_422_parse(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        content=b"@prefix this is not Turtle",
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "E_OWL_PARSE"


def test_import_json_shape_mismatch_returns_422(client: TestClient, session_token: str) -> None:
    """JSON content-type with an unrecognised body shape (e.g.
    ``{not_turtle: ...}``) must fail loudly rather than silently
    falling back to "treat the JSON bytes as Turtle".
    """

    resp = client.post(
        "/mapping/import-owl",
        json={"not_turtle": "oops"},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "E_OWL_BAD_JSON"


def test_import_non_utf8_body_returns_422(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/import-owl",
        content=b"\xff\xfe not utf8 bytes",
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "E_OWL_NOT_UTF8"


def test_import_empty_json_envelope_returns_422(client: TestClient, session_token: str) -> None:
    """``{turtle: ""}`` must fail with E_OWL_EMPTY_BODY rather
    than silently importing an empty bundle.
    """

    resp = client.post(
        "/mapping/import-owl",
        json={"turtle": ""},
        headers={"X-Arango-Session": session_token},
    )
    # Pydantic min_length=1 fires first → 422.
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# OWL-bomb defences (PRD §8.6 T7)
# ---------------------------------------------------------------------------


def test_byte_ceiling_returns_413(
    client: TestClient,
    session_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body larger than ``MAPPING_IMPORT_MAX_BYTES`` must be
    short-circuited with 413 before the parser runs.
    """

    monkeypatch.setenv("MAPPING_IMPORT_MAX_BYTES", "100")
    big_body = b"a" * 200
    resp = client.post(
        "/mapping/import-owl",
        content=big_body,
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["code"] == "E_OWL_TOO_LARGE"
    assert detail["max_bytes"] == 100
    assert detail["actual_bytes"] == 200


def test_triple_cap_returns_422(
    client: TestClient,
    session_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body that parses to more triples than
    ``MAPPING_IMPORT_MAX_TRIPLES`` must return 422 with the typed
    code ``E_OWL_TOO_LARGE``.
    """

    monkeypatch.setenv("MAPPING_IMPORT_MAX_TRIPLES", "3")
    resp = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "E_OWL_TOO_LARGE"
    assert "MAPPING_IMPORT_MAX_TRIPLES" in detail["error"]


def test_byte_ceiling_default_does_not_block_normal_imports(client: TestClient, session_token: str) -> None:
    """Sanity check — the 2 MB default must not block a small
    fixture (regression guard against someone setting the default
    to 1).
    """

    resp = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "raw,blocks",
    [
        ("100", True),
        ("0", False),
        ("-5", False),
        ("garbage", False),
        ("", False),
    ],
)
def test_byte_ceiling_env_parsing(
    client: TestClient,
    session_token: str,
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    blocks: bool,
) -> None:
    """The byte-cap parser must default to a generous value rather
    than to "no cap" when the env value is garbage — same defer-
    rather-than-bypass posture as the analyzer-required parser.
    """

    monkeypatch.setenv("MAPPING_IMPORT_MAX_BYTES", raw)
    big_body = b"a" * 500
    resp = client.post(
        "/mapping/import-owl",
        content=big_body,
        headers={
            "Content-Type": "text/turtle",
            "X-Arango-Session": session_token,
        },
    )
    if blocks:
        assert resp.status_code == 413
    else:
        # Either 200 (parses to empty bundle) or 422 (parse error
        # for the "aaaa…" body) — both are "not 413".
        assert resp.status_code != 413


# ---------------------------------------------------------------------------
# Happy path — export
# ---------------------------------------------------------------------------


def test_export_json_envelope(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mime_type"] == "text/turtle"
    assert body["triple_count"] > 0
    assert "Person" in body["turtle"]
    assert "knows" in body["turtle"]
    assert isinstance(body["elapsed_ms"], (int, float))


def test_export_turtle_content_negotiation(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
        headers={
            "X-Arango-Session": session_token,
            "Accept": "text/turtle",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/turtle")
    assert "Person" in resp.text
    # Triple count is surfaced in a header so a Turtle-only client
    # can still see it without parsing the body.
    assert int(resp.headers["x-triple-count"]) > 0


def test_export_with_mapping_dict(client: TestClient, session_token: str) -> None:
    """The preferred input shape is the ``mapping`` wire dict —
    test it round-trips through the synthesizer to a non-empty
    Turtle blob."""

    mapping = {
        "physicalMapping": {
            "entities": {
                "Person": {
                    "style": "COLLECTION",
                    "collectionName": "Person",
                }
            },
            "relationships": {},
        },
        "metadata": {},
    }
    resp = client.post(
        "/mapping/export-owl",
        json={"mapping": mapping},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Person" in body["turtle"]
    assert body["triple_count"] >= 2  # at least owl:Class + phys:collectionName


def test_export_without_mapping_or_ttl_returns_422(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/export-owl",
        json={},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "E_OWL_EXPORT_EMPTY"


def test_export_propagates_owl_bomb_via_ontology_ttl(
    client: TestClient,
    session_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the export takes the ``ontology_ttl`` round-trip path,
    the same triple cap applies.
    """

    monkeypatch.setenv("MAPPING_IMPORT_MAX_TRIPLES", "3")
    resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "E_OWL_TOO_LARGE"


def test_export_malformed_ontology_ttl_returns_422_parse(client: TestClient, session_token: str) -> None:
    resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": "@@ not Turtle @@"},
        headers={"X-Arango-Session": session_token},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "E_OWL_PARSE"


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_import_export_import_round_trip(client: TestClient, session_token: str) -> None:
    """Import → Export → Import must yield the same entity surface."""

    headers = {"X-Arango-Session": session_token}

    r1 = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={**headers, "Content-Type": "text/turtle"},
    )
    assert r1.status_code == 200
    mapping_dict = r1.json()["mapping"]

    r2 = client.post(
        "/mapping/export-owl",
        json={"mapping": mapping_dict},
        headers=headers,
    )
    assert r2.status_code == 200
    exported = r2.json()["turtle"]

    r3 = client.post(
        "/mapping/import-owl",
        content=exported.encode("utf-8"),
        headers={**headers, "Content-Type": "text/turtle"},
    )
    assert r3.status_code == 200
    re_imported = r3.json()["mapping"]["physicalMapping"]
    original = mapping_dict["physicalMapping"]
    assert set(re_imported["entities"]) == set(original["entities"])
    assert set(re_imported["relationships"]) == set(original["relationships"])


# ---------------------------------------------------------------------------
# OpenAPI registration
# ---------------------------------------------------------------------------


def test_openapi_registers_both_routes(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/mapping/import-owl" in paths
    assert "post" in paths["/mapping/import-owl"]
    assert "/mapping/export-owl" in paths
    assert "post" in paths["/mapping/export-owl"]


def test_openapi_documents_response_shapes(client: TestClient) -> None:
    """Only the import response is registered as a Pydantic
    response_model — the export route declares ``response_model=None``
    so that the same handler can return either a JSON envelope or
    a raw ``text/turtle`` response based on content negotiation
    (FastAPI cannot represent a union of ``BaseModel`` and
    ``PlainTextResponse`` in OpenAPI). The export response shape
    is documented in :class:`OwlExportResponse` for typed clients
    even though the spec declares it as a generic ``object``.
    """

    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "OwlImportResponse" in schemas
    # Export route declares response_model=None on purpose; the
    # OpenAPI entry should still exist with a 200 response, just
    # without a strict response schema.
    export_op = spec["paths"]["/mapping/export-owl"]["post"]
    assert "responses" in export_op
    assert "200" in export_op["responses"]


# ---------------------------------------------------------------------------
# Env-var parsing helper (direct unit test)
# ---------------------------------------------------------------------------


def test_resolve_max_bytes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from arango_sparql.service.models import _DEFAULT_MAPPING_IMPORT_MAX_BYTES
    from arango_sparql.service.routes.mapping import _resolve_max_bytes

    monkeypatch.delenv("MAPPING_IMPORT_MAX_BYTES", raising=False)
    assert _resolve_max_bytes() == _DEFAULT_MAPPING_IMPORT_MAX_BYTES


@pytest.mark.parametrize(
    "raw,expected_default",
    [
        ("garbage", True),
        ("0", True),
        ("-5", True),
        ("", True),
        ("100", False),
    ],
)
def test_resolve_max_bytes_env_parsing(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected_default: bool
) -> None:
    from arango_sparql.service.models import _DEFAULT_MAPPING_IMPORT_MAX_BYTES
    from arango_sparql.service.routes.mapping import _resolve_max_bytes

    monkeypatch.setenv("MAPPING_IMPORT_MAX_BYTES", raw)
    if expected_default:
        assert _resolve_max_bytes() == _DEFAULT_MAPPING_IMPORT_MAX_BYTES
    else:
        assert _resolve_max_bytes() == int(raw)


# ---------------------------------------------------------------------------
# RDF/XML Content-Type/Accept negotiation (04-02 Task 2)
# ---------------------------------------------------------------------------


def test_import_rdfxml_body_matches_turtle_import(client: TestClient, session_token: str) -> None:
    """POST /mapping/import-owl with Content-Type: application/rdf+xml
    must parse an RDF/XML body and return the same entity/relationship
    surface as the Turtle import of the same ontology (D-04)."""

    turtle_resp = client.post(
        "/mapping/import-owl",
        content=PG_TURTLE.encode("utf-8"),
        headers={"Content-Type": "text/turtle", "X-Arango-Session": session_token},
    )
    assert turtle_resp.status_code == 200, turtle_resp.text

    xml_resp = client.post(
        "/mapping/import-owl",
        content=PG_RDFXML.encode("utf-8"),
        headers={"Content-Type": "application/rdf+xml", "X-Arango-Session": session_token},
    )
    assert xml_resp.status_code == 200, xml_resp.text

    turtle_pm = turtle_resp.json()["mapping"]["physicalMapping"]
    xml_pm = xml_resp.json()["mapping"]["physicalMapping"]
    assert xml_pm["entities"] == turtle_pm["entities"]
    assert xml_pm["relationships"] == turtle_pm["relationships"]


def test_export_rdfxml_accept_negotiation(client: TestClient, session_token: str) -> None:
    """POST /mapping/export-owl with Accept: application/rdf+xml must
    return a raw RDF/XML body (re-parseable under rdflib format="xml")
    with a matching Content-Type."""

    resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
        headers={
            "X-Arango-Session": session_token,
            "Accept": "application/rdf+xml",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/rdf+xml")
    g = Graph()
    g.parse(data=resp.text, format="xml")
    assert len(g) > 0
    assert int(resp.headers["x-triple-count"]) > 0


def test_export_turtle_default_path_unchanged(client: TestClient, session_token: str) -> None:
    """Existing Turtle import/export path must be unaffected by the
    new format-negotiation machinery — default Accept still yields the
    JSON envelope; Accept: text/turtle still yields raw Turtle."""

    json_resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
        headers={"X-Arango-Session": session_token},
    )
    assert json_resp.status_code == 200
    assert json_resp.json()["mime_type"] == "text/turtle"

    turtle_resp = client.post(
        "/mapping/export-owl",
        json={"ontology_ttl": PG_TURTLE},
        headers={"X-Arango-Session": session_token, "Accept": "text/turtle"},
    )
    assert turtle_resp.status_code == 200
    assert turtle_resp.headers["content-type"].startswith("text/turtle")


def test_import_rdfxml_owl_bomb_returns_422(
    client: TestClient,
    session_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The OWL-bomb triple cap must fire identically for an RDF/XML
    body — mirrors test_triple_cap_returns_422 but posting
    application/rdf+xml."""

    monkeypatch.setenv("MAPPING_IMPORT_MAX_TRIPLES", "3")
    resp = client.post(
        "/mapping/import-owl",
        content=PG_RDFXML.encode("utf-8"),
        headers={
            "Content-Type": "application/rdf+xml",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "E_OWL_TOO_LARGE"


# ---------------------------------------------------------------------------
# RDF/XML pre-parse DOCTYPE/ENTITY guard (04-02 Task 3)
# ---------------------------------------------------------------------------


def test_import_rdfxml_doctype_entity_returns_422_parse(client: TestClient, session_token: str) -> None:
    """POST /mapping/import-owl with a DOCTYPE/ENTITY RDF/XML body must
    return 422 E_OWL_PARSE via the unchanged envelope — the billion-
    laughs/XXE payload must never reach rdflib's parser."""

    resp = client.post(
        "/mapping/import-owl",
        content=_XML_BILLION_LAUGHS.encode("utf-8"),
        headers={
            "Content-Type": "application/rdf+xml",
            "X-Arango-Session": session_token,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "E_OWL_PARSE"


# Suppress unused-import warning on `os` (kept for potential
# future env manipulation across the file).
_ = os
