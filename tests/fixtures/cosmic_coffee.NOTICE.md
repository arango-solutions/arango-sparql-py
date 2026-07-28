# Microsoft Ontology Playground — cosmic-coffee fixture — Attribution Notice

This directory vendors a single fixture derived from the **Microsoft
Ontology Playground** catalogue, used as the file-based OWL round-trip
fixture for Phase 4's `REQ-thirdparty-tool-compat` (D-06).

- **Title:** cosmic-coffee.rdf (Ontology Playground catalogue —
  "Fourth Coffee" sample ontology: a modern coffee shop chain with
  suppliers, products, stores, customers, and orders).
- **Source:** https://github.com/microsoft/Ontology-Playground
  (path: `catalogue/official/cosmic-coffee/cosmic-coffee.rdf`)
- **Commit:** `9a0eb93cef978b1ee6c4a6857dc0ce2733444ea0` (last commit that
  touched this file on `main`, resolved via the GitHub API `commits`
  endpoint fetched 2026-07-28; committed 2026-06-03).
- **License:** MIT (verified via the GitHub API repo endpoint's
  `license.spdx_id: "MIT"` field, fetched 2026-07-28).

## Files vendored

- `cosmic_coffee.rdf` — verbatim copy, 26,981 bytes / 349 triples (6
  `owl:Class`, 7 `owl:ObjectProperty`, 36 `owl:DatatypeProperty`
  declarations), fetched from
  `raw.githubusercontent.com/microsoft/Ontology-Playground/main/catalogue/official/cosmic-coffee/cosmic-coffee.rdf`
  and confirmed to parse as valid RDF/XML via `rdflib.Graph.parse(...,
  format="xml")` (triple count verified by direct parse this session).

## Changes made

- None. The file is checked in verbatim, pinned to the commit SHA above,
  and is never fetched live at test time (supply-chain control — see
  `04-RESEARCH.md` "Known Threat Patterns" / T-04-01 in the plan's
  threat model).

## Downstream use

`tests/integration/test_ontology_playground_roundtrip.py` (Plan 05)
round-trips this fixture through `POST /mapping/import-owl` ->
`POST /mapping/export-owl` and asserts `rdflib.Graph.isomorphic()`
equality (D-06). This fixture has no `phys:collectionName` annotations
and is intentionally **not** reused for the AOE own-half contract test
(`tests/integration/test_aoe_roundtrip.py`), which needs a
`phys:`-annotated ontology to resolve at `/sparql` — see RESEARCH.md
Pitfall 3.
