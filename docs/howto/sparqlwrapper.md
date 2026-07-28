# How-to: SPARQLWrapper (pure-Python SPARQL client)

[SPARQLWrapper](https://sparqlwrapper.readthedocs.io/) is a pure-Python
`urllib`-based SPARQL client — PRD §11.1 names it as an automated
compatibility target, and it already has a real, Docker-gated smoke test:
[`tests/integration/test_sparqlwrapper_smoke.py`](../../tests/integration/test_sparqlwrapper_smoke.py)
(D-06). This recipe mirrors that test's exact SELECT/ASK/Service
Description flow as a reproducible manual companion — useful for a quick
interactive check without running `pytest`.

## Prerequisites

```bash
pip install "SPARQLWrapper>=2.0.0"   # already a [dev] extra in this repo:
                                       # uv sync --extra dev
```

- Our service running and reachable, with ArangoDB up:
  ```bash
  docker compose up -d arangodb     # host 8532 -> container 8529
  uv run python main.py             # defaults to http://localhost:8000
  ```
- A schema/mapping activated for the collection you want to query. The
  automated test seeds a dedicated `SparqlwrapperPerson` collection and
  activates its bundle via `SchemaCache.put()` (see the test file's
  docstring) so `/sparql` can resolve it deterministically without relying
  on heuristic auto-detection — if you're pointing this recipe at your own
  data instead, make sure an equivalent OWL mapping has been imported
  (`POST /mapping/import-owl`) or otherwise activated first.

## Connect

`POST /connect` to obtain a bearer session token:

```python
import json
import urllib.request

body = json.dumps(
    {
        "url": "http://localhost:8529",   # your ArangoDB URL
        "database": "sparql-to-aql",       # never _system
        "username": "root",
        "password": "<your-password>",
    }
).encode("utf-8")

req = urllib.request.Request(
    "http://localhost:8000/connect",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=5.0) as resp:
    token = json.loads(resp.read().decode("utf-8"))["token"]
```

## SELECT

```python
from SPARQLWrapper import JSON, POST, SPARQLWrapper

sparql = SPARQLWrapper("http://localhost:8000/sparql")
sparql.setMethod(POST)
sparql.setReturnFormat(JSON)
sparql.addCustomHttpHeader("Authorization", f"Bearer {token}")

sparql.setQuery(
    "PREFIX : <http://example.org/sw#> "
    "SELECT ?s ?n WHERE { ?s a :SparqlwrapperPerson ; :name ?n }"
)
results = sparql.query().convert()
# results["results"]["bindings"] is a list of {"s": {...}, "n": {...}} dicts,
# one per matching row — exactly the shape asserted by
# test_sparqlwrapper_select_returns_seeded_bindings in the automated test.
```

## ASK

```python
sparql.setQuery(
    'PREFIX : <http://example.org/sw#> ASK { ?s a :SparqlwrapperPerson ; :name "Frank" }'
)
ask_result = sparql.query().convert()
# ask_result["boolean"] is a real Python bool (True/False), per the SPARQL
# 1.1 Query Results JSON Format — matching
# test_sparqlwrapper_ask_returns_boolean's assertion.
```

## Service Description

```python
import urllib.request

with urllib.request.urlopen("http://localhost:8000/sparql", timeout=5.0) as resp:
    assert resp.status == 200
    assert resp.headers.get("Content-Type", "").startswith("text/turtle")
    body = resp.read().decode("utf-8")
assert "sparql-service-description" in body
```

An unauthenticated `GET /sparql` with no `query` parameter returns the
SPARQL 1.1 Service Description document as `text/turtle` — no bearer token
needed, matching `test_service_description_over_real_socket`.

## Reproducing the automated test directly

The exact same flow (over a real bound `uvicorn` socket rather than a
manually-run `main.py` process) runs in CI/local dev via:

```bash
RUN_INTEGRATION=1 uv run pytest -q -m integration \
  tests/integration/test_sparqlwrapper_smoke.py
```

This is the canonical, CI-proven version of the recipe above — the manual
walkthrough here is a companion for interactive exploration, not a
replacement for the automated test.
