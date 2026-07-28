# How-to: Microsoft Ontology Playground (RDF/XML roundtrip)

The [Ontology Playground](https://github.com/microsoft/Ontology-Playground)
project is a catalogue of curated OWL ontologies, distributed as files (no
running app to install). This recipe documents a file-based RDF/XML
import → export roundtrip through our `/mapping` routes using the vendored
`cosmic_coffee.rdf` catalogue fixture (MIT, 349 triples — see
[`tests/fixtures/cosmic_coffee.NOTICE.md`](../../tests/fixtures/cosmic_coffee.NOTICE.md)
for provenance) — already exercised by an automated, Docker-gated test:
[`tests/integration/test_ontology_playground_roundtrip.py`](../../tests/integration/test_ontology_playground_roundtrip.py)
(D-06). This recipe mirrors that test's exact flow as a reproducible manual
companion.

This is a **pure OWL fidelity** check — no `/sparql` query is involved, no
`phys:collectionName` physical-mapping annotations are required. (Contrast
with the AOE own-half contract test, which needs a `phys:`-annotated
fixture instead — see `tests/integration/test_aoe_roundtrip.py`.)

## Prerequisites

- Our service running and reachable:
  ```bash
  uv run python main.py             # defaults to http://localhost:8000
  ```
  ArangoDB does not strictly need to be up for this recipe (the roundtrip
  is file-based, no `/sparql` query), but `/mapping/import-owl` and
  `/mapping/export-owl` both require an authenticated session, which in
  turn requires a real `/connect` target — so start ArangoDB too if you
  don't already have another way to satisfy `/connect`:
  ```bash
  docker compose up -d arangodb     # host 8532 -> container 8529
  ```
- The vendored fixture: `tests/fixtures/cosmic_coffee.rdf` (already checked
  into this repo).

## Connect

```bash
curl -s -X POST http://localhost:8000/connect \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:8529", "database": "sparql-to-aql", "username": "root", "password": "<your-password>"}'
# -> {"token": "...", ...}
```

## Import (RDF/XML)

```bash
TOKEN="<paste the token from /connect above>"

curl -s -X POST http://localhost:8000/mapping/import-owl \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/rdf+xml" \
  --data-binary @tests/fixtures/cosmic_coffee.rdf \
  > /tmp/imported.json

# imported.json carries: {"accepted": true, "triple_count": 349, "mapping": {...}}
```

The `mapping` field in the response is the wire-dict `MappingBundle` — save
it (`.mapping` above) to feed into the export step next.

## Export (RDF/XML)

```bash
python3 -c "
import json
with open('/tmp/imported.json') as f:
    mapping_wire = json.load(f)['mapping']
print(json.dumps({'mapping': mapping_wire}))
" > /tmp/export_request.json

curl -s -X POST http://localhost:8000/mapping/export-owl \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/rdf+xml" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/export_request.json \
  > /tmp/exported.rdf
```

## Verifying isomorphism (the actual fidelity check)

```python
from rdflib import Graph

original = Graph()
original.parse("tests/fixtures/cosmic_coffee.rdf", format="xml")

reexported = Graph()
reexported.parse("/tmp/exported.rdf", format="xml")

assert original.isomorphic(reexported), "roundtrip is not blank-node-safe isomorphic"
print("OK: roundtrip is isomorphic,", len(original), "triples")
```

`Graph.isomorphic()` compares two RDF graphs for equality up to blank-node
renaming — exactly what "triple-bag equality" (D-03/D-04's wording) means
for OWL fixtures containing blank nodes.

## Reproducing the automated test directly

```bash
RUN_INTEGRATION=1 uv run pytest -q -m integration \
  tests/integration/test_ontology_playground_roundtrip.py
```

The automated test additionally cross-checks the `x-triple-count` response
header on the export call against the original fixture's triple count as a
cheap, independent sanity check alongside the isomorphism assertion. This
is the canonical, CI-proven version of the recipe above.
