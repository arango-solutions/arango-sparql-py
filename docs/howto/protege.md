# How-to: Protégé (JVM desktop ontology editor)

[Protégé](https://protege.stanford.edu/) is a JVM desktop application; it
cannot run headlessly and is never installed in CI (D-07). This recipe
documents (a) how to point Protégé's own SPARQL Query panel at our live
`/sparql` endpoint interactively, and (b) the headless-equivalent
verification via Apache Jena's `rsparql` CLI (see
[`arq.md`](arq.md) for the full `rsparql` reference) — since Protégé itself
can't be automated, `rsparql` drives and records the identical SPARQL 1.1
Protocol wire traffic Protégé's panel would send, which is what gets
recorded as this recipe's transcript.

**No JVM image is added to CI.** This recipe is documented-manual only,
verified by a human running the real desktop app (and/or `rsparql`) against
a live instance of this service.

## Prerequisites

- Protégé 5.x desktop application, downloaded from
  [protege.stanford.edu/software.php](https://protege.stanford.edu/software.php)
  (requires a JVM; Protégé ships its own bundled JRE on most platforms).
  The "SPARQL Query" tab/plugin ships with modern Protégé builds by default
  — no extra plugin install should be needed.
- Apache Jena's `rsparql` CLI installed (see [`arq.md`](arq.md)
  Prerequisites) — this is the headless driver used to record the
  transcript below, since Protégé's own GUI panel cannot be scripted.
- Our service running and reachable, with ArangoDB up:
  ```bash
  docker compose up -d arangodb     # host 8532 -> container 8529
  uv run python main.py             # defaults to http://localhost:8000
  ```
- An active, schema-activated session (`POST /connect`) — see
  [`sparqlwrapper.md`](sparqlwrapper.md#connect) for the exact request body
  and how to obtain a bearer token.

## Connect

**Interactively, in Protégé:** open the "SPARQL Query" tab, enter our
endpoint URL (`http://localhost:8000/sparql`) as the query service target,
and (if your Protégé build's SPARQL panel supports custom HTTP headers)
set `Authorization: Bearer <token>` to the token returned by `/connect`.
Some Protégé SPARQL-panel builds don't expose a custom-header field; in
that case, query the endpoint's unauthenticated surfaces (the Service
Description) directly, and use the headless `rsparql` path below for
authenticated SELECT/ASK queries.

**Headlessly, via `rsparql`** (the actual driver used to record this
recipe's transcript):

```bash
rsparql --service http://localhost:8000/sparql \
  --query 'ASK { ?s ?p ?o }'
```

## SELECT

In Protégé's SPARQL Query tab, enter a query such as:

```sparql
PREFIX : <http://example.org/>
SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }
```

and click "Execute". The headless equivalent (what actually produced the
recorded transcript below):

```bash
rsparql --service http://localhost:8000/sparql \
  --query 'PREFIX : <http://example.org/> SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }' \
  --results JSON
```

## ASK

```bash
rsparql --service http://localhost:8000/sparql \
  --query 'ASK { ?s ?p ?o }'
```

Protégé's panel: same query text, same "Execute" button; the response
renders as a boolean result in the results pane.

## Service Description

```bash
curl -s -H "Accept: text/turtle" http://localhost:8000/sparql | head -40
```

Confirm the response is `text/turtle` and contains
`sparql-service-description`. Protégé's SPARQL panel typically fetches
this automatically when you point it at a new endpoint URL, to discover
supported query features.

## Transcript (recorded, human-required checkpoint)

**This section must be filled in by a human** running the SELECT, ASK, and
Service Description flow above against a live instance of this service —
either via Protégé's own SPARQL panel, via `rsparql`, or both. Paste the
actual observed output. **Do not fabricate this section.** Confirm no
secret, API key, or session token appears anywhere in the pasted output
before committing.

```text
<!-- RECORDED TRANSCRIPT — TO BE FILLED IN BY A HUMAN.

Run the following against a live instance of this service and paste the
REAL terminal / Protégé UI output below each command. Do not invent
output.

1) SELECT:
   $ rsparql --service http://localhost:8000/sparql \
       --query 'PREFIX : <http://example.org/> SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }' \
       --results JSON
   [PASTE ACTUAL OUTPUT HERE]

2) ASK:
   $ rsparql --service http://localhost:8000/sparql --query 'ASK { ?s ?p ?o }'
   [PASTE ACTUAL OUTPUT HERE]

3) Service Description:
   $ curl -s -H "Accept: text/turtle" http://localhost:8000/sparql | head -40
   [PASTE ACTUAL OUTPUT HERE]

Confirm: no API key / session token / internal-only URL appears above.
-->
```
