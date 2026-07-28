# How-to: connecting third-party SPARQL tooling

This directory hosts short, task-focused recipes for connecting external
SPARQL tools and clients to `arango-sparql-py`'s W3C SPARQL 1.1 Protocol
endpoint (`POST`/`GET /sparql`). It is the documentation half of
`REQ-thirdparty-tool-compat` (PRD §11.2-§11.4): cheap, high-value clients
get an automated smoke test under `tests/integration/`; JVM/browser-heavy
tools are documented here with a recorded transcript instead (D-05/D-07).

See PRD §11.1 for the full list of tools this project targets for
interoperability, and §11.4 for the connectivity-recipe posture.

## Planned recipes

| Recipe | Tool | Purpose |
|--------|------|---------|
| `sparqlwrapper.md` | [SPARQLWrapper](https://sparqlwrapper.readthedocs.io/) (Python) | Pure-Python SPARQL client; also exercised by an automated smoke test (`tests/integration/test_sparqlwrapper_smoke.py`, D-06) — this recipe documents the same SELECT/ASK/Service-Description flow for manual use. |
| `ontology-playground.md` | Microsoft [Ontology Playground](https://github.com/microsoft/Ontology-Playground) | Round-tripping a vendored OWL/RDF-XML catalogue fixture through `/mapping/import-owl` and `/mapping/export-owl` (D-06); companion to `tests/integration/test_ontology_playground_roundtrip.py`. |
| `protege.md` | [Protégé](https://protege.stanford.edu/) (JVM desktop ontology editor) | Connecting Protégé to the live `/sparql` endpoint for interactive querying; documented-manual only, no CI image (D-07). |
| `arq.md` | Apache Jena `rsparql`/`arq` CLI | Headless command-line SPARQL querying against `/sparql`, used to drive and record the Protégé recipe's transcript; documented-manual only (D-07). |
| `yasgui.md` | [YASGUI](https://triply.cc/docs/yasgui) (browser SPARQL widget) | Embedding a browser-based query UI against `/sparql`; documented-manual only, no CI image (D-07). |

Each recipe (once written) follows a consistent shape: Prerequisites,
Connect, SELECT example, ASK example, Service Description fetch, and a
recorded transcript proving the flow was actually run against a live
instance of this service.
