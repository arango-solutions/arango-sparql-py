# How-to: Apache Jena `rsparql` CLI (headless SPARQL querying)

Apache Jena's command-line SPARQL client, used both as a standalone
headless tool and as the driver behind the [`docs/howto/protege.md`](protege.md)
recipe (Protégé itself is a JVM desktop GUI and cannot run headlessly in
CI — `rsparql` exercises the identical W3C SPARQL 1.1 Protocol wire
traffic that Protégé's own "SPARQL Query" panel would send). Documented-
manual only per D-07 — **no JVM image is added to CI**.

> **Naming note (04-RESEARCH.md Assumption A1):** two official Apache Jena
> doc pages disagree slightly on the "canonical" tool name for remote
> querying (`cmds.html` calls it `arq.remote`; `sparql-remote.html` and this
> project's own verified `brew install jena` + `--help` run both confirm the
> actual shipped binary is **`rsparql`**, not `arq`). This file is named
> `arq.md` for historical reasons (it documents the Apache Jena toolkit,
> which also ships a separate local-file-only `arq` binary), but every
> command below against our live `/sparql` endpoint uses `rsparql`. Do not
> substitute `arq` for `--service` queries — `arq` only queries local
> files/datasets, it has no `--service` flag.

## Prerequisites

- Apache Jena installed locally (developer machine only, never CI):
  ```bash
  brew install jena   # macOS; installs rsparql, arq, sparql, riot, etc.
  ```
  Or download the official tarball from
  [jena.apache.org/download](https://jena.apache.org/download/) and put its
  `bin/` on your `PATH`.
- Our service running and reachable, with ArangoDB up:
  ```bash
  docker compose up -d arangodb     # host 8532 -> container 8529
  uv run python main.py             # defaults to http://localhost:8000
  ```
- An active session: `POST /connect` (see
  [`sparqlwrapper.md`](sparqlwrapper.md#connect) for the exact request body)
  with a schema/mapping activated so `/sparql` has something to query
  against. `rsparql` itself does not need the session token for an
  unauthenticated Service Description fetch (`GET /sparql`, no query), but a
  SELECT/ASK against real data does need a connected + schema-activated
  session, exactly like every other client in this directory.

## Connect

`rsparql`'s `--service` flag points it at any SPARQL 1.1 Protocol endpoint:

```bash
rsparql --service http://localhost:8000/sparql \
  --query 'ASK { ?s ?p ?o }'
```

If your endpoint requires the `Authorization: Bearer <token>` header (our
`/sparql` route accepts it the same way `SPARQLWrapper`'s
`addCustomHttpHeader` does — see `sparqlwrapper.md`), pass it via
`--set` / an HTTP header flag your Jena build supports, or front the
request with a local reverse proxy that injects the header. Consult
`rsparql --help` for the exact flag your installed Jena version exposes —
this varies slightly by release.

## SELECT

```bash
rsparql --service http://localhost:8000/sparql \
  --query 'PREFIX : <http://example.org/> SELECT ?s ?n WHERE { ?s a :Person ; :name ?n }' \
  --results JSON
```

`--results` accepts `text` (human-readable table, the default), `XML`,
`JSON`, `CSV`, or `TSV`. Use `JSON` to match the SPARQL 1.1 Query Results
JSON Format our `/sparql` route itself emits.

## ASK

```bash
rsparql --service http://localhost:8000/sparql \
  --query 'ASK { ?s ?p ?o }'
```

A bare `ASK { ?s ?p ?o }` is a good connectivity smoke check: it returns
`true` the moment the target dataset (or, for us, the connected
ArangoDB collection) has at least one matching triple.

## Service Description

Our `/sparql` route serves a SPARQL 1.1 Service Description document on an
unauthenticated `GET` with no `query` parameter, as `text/turtle`. `rsparql`
itself is a query client (it always sends a `query=`), so to fetch the bare
Service Description use a plain HTTP client instead:

```bash
curl -s -H "Accept: text/turtle" http://localhost:8000/sparql | head -40
```

Look for `sparql-service-description` in the output — that's what proves
the endpoint is correctly advertising its SPARQL 1.1 Protocol capabilities.

## Transcript (optional)

The Protégé recipe ([`protege.md`](protege.md)) is the plan-required
recorded-transcript deliverable for the `rsparql`-headless flow. If you'd
also like a standalone `rsparql`-only transcript here, paste the actual
terminal output below — **do not fabricate this section**; leave it as-is
if you are not recording it here.

```text
<!-- OPTIONAL — RECORDED TRANSCRIPT PLACEHOLDER.
     If recorded, paste the real terminal output of the SELECT, ASK, and
     Service Description commands above, run against a live instance of
     this service. Do not invent output. Confirm no secret/API key/session
     token appears before committing. Leave this block untouched if you
     are only recording the transcript in protege.md. -->
```
