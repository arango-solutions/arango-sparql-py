# How-to: YASGUI (browser SPARQL widget)

[YASGUI](https://triply.cc/docs/yasgui) ("Yet Another SPARQL GUI") is a
browser-based SPARQL query widget. It runs entirely client-side (no server
component of its own) and is never installed in CI — this recipe is
documented-manual only (D-07), verified by a human pointing a real browser
at our live `/sparql` endpoint.

**No browser image is added to CI.**

## Prerequisites

- A modern browser (any current Chrome/Firefox/Safari/Edge).
- Our service running and reachable, with ArangoDB up:
  ```bash
  docker compose up -d arangodb     # host 8532 -> container 8529
  uv run python main.py             # defaults to http://localhost:8000
  ```
- An active, schema-activated session (`POST /connect`) — see
  [`sparqlwrapper.md`](sparqlwrapper.md#connect) for the exact request body
  and how to obtain a bearer token.
- A YASGUI instance. Two ways to get one, either is fine for this recipe:
  1. **Hosted demo** — [yasgui.triply.cc](https://yasgui.triply.cc/) (fastest
     to try; CORS must be permitted by our service for the browser to reach
     `http://localhost:8000/sparql` from a different origin).
  2. **Local embed** — install the npm package and serve a minimal HTML
     page:
     ```bash
     npm install @triply/yasgui
     ```
     > **Maintenance caveat (04-RESEARCH.md Assumption A3):** at research
     > time, `@matdata/yasgui` (a maintained fork, currently at 5.20.3) was
     > identified as a plausible current successor to the original
     > `@triply/yasgui` (4.2.28), which appears less actively maintained.
     > This is a low-risk, documented-manual-only concern (no automated
     > test depends on which package you pick) — check both packages'
     > current npm/GitHub activity before choosing one for a long-lived
     > local embed, and prefer whichever is actively maintained at the time
     > you set this up.

## Connect

Open your YASGUI instance and set the query endpoint (usually a field
labeled "Endpoint" or configured via the `requestConfig.endpoint` option in
a local embed) to:

```
http://localhost:8000/sparql
```

If your `/sparql` session requires the `Authorization: Bearer <token>`
header (obtained from `POST /connect`, same as every other client in this
directory), YASGUI's request-headers configuration
(`requestConfig.headers`, or the endpoint-config UI's custom-headers field
depending on your YASGUI version) is where to add it. Consult your
installed YASGUI version's docs for the exact option name.

## SELECT

Enter into the query editor:

```sparql
PREFIX : <http://example.org/>
SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }
```

and click the run button (▶). Results render as a table in YASGUI's
results pane, with column headers matching the SELECT's variable names.

## ASK

```sparql
ASK { ?s ?p ?o }
```

YASGUI renders ASK results as a boolean (`true`/`false`) rather than a
table.

## Service Description

YASGUI is a query-execution widget, not a generic HTTP client — it always
sends a `query=` parameter. To fetch the bare Service Description document
(an unauthenticated `GET /sparql` with no query), use a separate browser
tab or `curl`:

```bash
curl -s -H "Accept: text/turtle" http://localhost:8000/sparql | head -40
```

Confirm the response is `text/turtle` and contains
`sparql-service-description`.

## Transcript (recorded, human-required checkpoint)

**This section must be filled in by a human** running the SELECT and ASK
queries above through a real YASGUI instance pointed at a live instance of
this service, plus the Service Description fetch. Paste the actual
observed output/screenshots-as-text below. **Do not fabricate this
section.** Confirm no secret, API key, or session token appears anywhere in
the pasted output before committing.

```text
<!-- RECORDED TRANSCRIPT — TO BE FILLED IN BY A HUMAN.

Run the following against a live instance of this service via a real
YASGUI instance (hosted or local embed) and paste the REAL observed output
below each item. Do not invent output.

1) SELECT (paste the resulting table's rows, or a description of what
   YASGUI displayed):
   Query: PREFIX : <http://example.org/> SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }
   [PASTE ACTUAL OUTPUT HERE]

2) ASK (paste the resulting boolean):
   Query: ASK { ?s ?p ?o }
   [PASTE ACTUAL OUTPUT HERE]

3) Service Description:
   $ curl -s -H "Accept: text/turtle" http://localhost:8000/sparql | head -40
   [PASTE ACTUAL OUTPUT HERE]

Confirm: no API key / session token / internal-only URL appears above.
-->
```
