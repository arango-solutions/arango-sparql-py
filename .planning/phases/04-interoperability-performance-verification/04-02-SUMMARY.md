---
phase: 04-interoperability-performance-verification
plan: 02
subsystem: api
tags: [rdflib, owl, rdf-xml, json-ld, n-triples, xxe, content-negotiation, fastapi]

# Dependency graph
requires:
  - phase: 04-01
    provides: perf/fixture/marker scaffolding (unrelated to this plan's code path, but same phase Wave-0 foundation)
provides:
  - "turtle_to_mapping/mapping_to_turtle format= kwarg (turtle/xml/json-ld/nt) covering PRD §11.3/§12.2's documented-but-unimplemented RDF/XML contract"
  - "POST /mapping/import-owl Content-Type negotiation (text/turtle, application/rdf+xml, application/ld+json, application/n-triples)"
  - "POST /mapping/export-owl Accept negotiation with matching Content-Type, JSON envelope path unchanged"
  - "Pre-parse RDF/XML DOCTYPE/ENTITY guard (billion-laughs/XXE defence) ahead of the post-parse triple cap"
affects: [04-04-aoe-roundtrip, 04-05-ontology-playground-roundtrip]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "owl.py _FORMAT_ALIASES / _resolve_rdflib_format / format_from_mime as the single MIME<->rdflib-format source of truth shared by owl.py and mapping.py"
    - "parse_owl_graph() centralizes parse + pre-parse DTD guard + OwlParseError wrapping so every RDF/XML entry point (import, export roundtrip reparse) inherits the guard automatically"

key-files:
  created: []
  modified:
    - arango_sparql/translate/owl.py
    - arango_sparql/service/routes/mapping.py
    - tests/translate/test_owl.py
    - tests/test_service_mapping_routes.py

key-decisions:
  - "MappingBundle.owl_turtle is re-serialised to canonical Turtle when importing from a non-Turtle format, preserving the codebase-wide invariant (resolver.py, schema routes) that owl_turtle is always Turtle text — a Rule 2 fix beyond the plan's literal text, since storing raw RDF/XML there would have silently broken every downstream consumer."
  - "The DOCTYPE/ENTITY guard lives in a shared parse_owl_graph() helper (not duplicated at each call site) so both turtle_to_mapping's import parse and the export route's roundtrip reparse inherit it automatically."
  - "Combined Task 1 (format dispatch) and Task 3's owl.py-side DTD guard into one commit since both modify the same parse call sites; Task 2's mapping.py negotiation plus Task 3's route-level 422 test landed in a second commit."

patterns-established:
  - "Format-dispatch tables belong in the lower (translate) layer and are re-exported as small pure functions (format_from_mime) for the route layer to consume, rather than routes reaching into private translate-layer names."

requirements-completed: []  # REQ-ontoextract-integration and REQ-thirdparty-tool-compat NOT marked complete here — their acceptance tests (tests/integration/test_aoe_roundtrip.py, tests/integration/test_*_compat.py) don't exist until Plans 04-03/04-04/04-05 land; this plan only unblocks them (mirrors the NL-FEW-01/NL-ACC-01 multi-plan-requirement precedent from Phase 07).

# Metrics
duration: 18min
completed: 2026-07-28
---

# Phase 04 Plan 02: OWL format-dispatch + RDF/XML security hardening Summary

**Closed the documented-but-unimplemented PRD §11.3/§12.2 RDF/XML contract via an rdflib format-dispatch table (Turtle/RDF-XML/JSON-LD/N-Triples, zero new deps) threaded through `turtle_to_mapping`/`mapping_to_turtle` and the `/mapping/import-owl`/`export-owl` routes, plus a pre-parse DOCTYPE/ENTITY guard closing the billion-laughs/XXE gap the post-parse triple cap couldn't catch.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-28T15:39:00Z
- **Completed:** 2026-07-28T15:53:00Z
- **Tasks:** 3 (2 code commits — Tasks 1 & 3's `owl.py` work combined, see Deviations)
- **Files modified:** 4

## Accomplishments

- `arango_sparql/translate/owl.py` gained a single `_FORMAT_ALIASES` MIME→rdflib-format table plus `_resolve_rdflib_format`/`format_from_mime`/`parse_owl_graph`, and both `turtle_to_mapping`/`mapping_to_turtle` accept a `format=` kwarg (default `"turtle"`) covering Turtle, RDF/XML (`xml`), JSON-LD (`json-ld`), and N-Triples (`nt`) — all native to the installed rdflib 7.6.
- `POST /mapping/import-owl` now negotiates the request `Content-Type` (raw-body path) into the resolved rdflib format and threads it into `turtle_to_mapping`; `POST /mapping/export-owl` negotiates the `Accept` header into an output format and sets a matching `Content-Type`, with the default (no/`*/*`/`application/json` Accept) JSON-envelope path byte-for-byte unchanged.
- A pre-parse `_reject_xml_dtd` guard rejects any RDF/XML payload containing `<!DOCTYPE`/`<!ENTITY` (case-insensitive, BOM-tolerant) before it ever reaches rdflib's SAX parser — proven against both a billion-laughs entity-expansion payload and an external-entity (`SYSTEM "file:///etc/passwd"`) payload, both raising `OwlParseError`/`E_OWL_PARSE` via the unchanged 422 envelope. The guard is centralised in `parse_owl_graph()` so it covers both the import parse site and the export route's triple-count roundtrip reparse.
- The post-parse OWL-bomb triple cap (`OwlBombError`/`E_OWL_TOO_LARGE`) is proven to fire identically regardless of import format (Turtle or RDF/XML), confirming it stays format-agnostic as designed.
- 33 new tests added (18 in `tests/translate/test_owl.py`, 6 in `tests/test_service_mapping_routes.py`, plus supporting fixtures); full existing suite (`tests/translate/test_owl.py` + `tests/test_service_mapping_routes.py`) is green at 101/101, and the broader non-integration suite is green at 1428/1428 with the W3C ≥96.4% coverage gate unaffected.

## Task Commits

Each task was committed atomically (Tasks 1 and 3's `owl.py`-side work combined into one commit — see Deviations):

1. **Task 1 + Task 3 (owl.py side): format-dispatch + DTD guard** - `b1ea4ea` (feat)
2. **Task 2 + Task 3 (route side): mapping.py negotiation + guard reuse** - `62e6211` (feat)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `arango_sparql/translate/owl.py` - `_FORMAT_ALIASES`/`_resolve_rdflib_format`/`format_from_mime`/`_reject_xml_dtd`/`parse_owl_graph`; `format=` kwarg on `turtle_to_mapping`/`mapping_to_turtle`; `owl_turtle` re-serialisation invariant fix
- `arango_sparql/service/routes/mapping.py` - `_read_import_body` returns negotiated format; `_wants_turtle_response` generalised to `_negotiate_export_format`; `import_owl`/`export_owl` thread the negotiated format through; `_EXPORT_MIME_BY_FORMAT` reverse-MIME table
- `tests/translate/test_owl.py` - RDF/XML/JSON-LD/N-Triples roundtrip parity tests, unknown-format tests, format-agnostic bomb-cap test, `format_from_mime` tests, billion-laughs/XXE/DTD-free tests
- `tests/test_service_mapping_routes.py` - RDF/XML import-matches-Turtle test, RDF/XML export Accept-negotiation test, unchanged-Turtle-default-path test, RDF/XML OWL-bomb test, RDF/XML DOCTYPE/ENTITY 422 test

## Decisions Made

- **`owl_turtle` invariant preserved across formats:** `MappingBundle.owl_turtle` is consumed elsewhere in the codebase (`resolver.py:403`, schema routes) under the hard assumption that it is always Turtle text. Storing the raw input verbatim regardless of import format (as a literal reading of the plan's action text might suggest) would have silently broken those consumers whenever a caller imported via `format="xml"`. Fixed by re-serialising the parsed graph to canonical Turtle before storage when the import format isn't already Turtle. Documented as a Rule 2 (missing critical functionality) auto-fix.
- **Shared `parse_owl_graph()` helper:** rather than duplicating the resolve→guard→parse→wrap-exception sequence at each of the three call sites (import, `mapping_to_turtle`'s owl_turtle reparse, and the export route's triple-count roundtrip reparse), all three route through one function. This also satisfies the plan's explicit requirement that the DTD guard cover "import + export roundtrip reparse" without hand-copying the guard call.
- **Tasks 1 and 3 combined in `owl.py`:** the format-dispatch table and the DTD guard both modify the same `turtle_to_mapping`/parse call sites; splitting them into two separate diffs on the same lines would have required an artificial two-pass edit with no review benefit, so they landed in one commit. Task 2 (route negotiation) plus the remainder of Task 3 (route-level 422 test, export-roundtrip guard reuse) landed in the second commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `MappingBundle.owl_turtle` re-serialised to Turtle for non-Turtle imports**
- **Found during:** Task 1 (format-dispatch implementation)
- **Issue:** The plan's literal action text says to preserve "the original Turtle" on `owl_turtle` when `preserve_owl=True`; with multi-format import, the "original" input for a `format="xml"` call is RDF/XML text, not Turtle. Storing it verbatim would silently corrupt every downstream consumer that assumes `owl_turtle` is Turtle (`resolver.py:403`'s `graph.parse(data=bundle.owl_turtle, format="turtle")`, plus the schema routes).
- **Fix:** When `preserve_owl=True` and the resolved format is not `"turtle"`, the already-parsed graph is re-serialised to canonical Turtle (`graph.serialize(format="turtle")`) before being stored on `owl_turtle`, keeping the format-agnostic invariant intact.
- **Files modified:** `arango_sparql/translate/owl.py` (`turtle_to_mapping`)
- **Verification:** `test_turtle_to_mapping_preserves_owl_turtle_as_turtle_even_for_xml_import` asserts the stored value contains no `<?xml` marker and re-parses cleanly as Turtle, isomorphic to the source graph.
- **Committed in:** `b1ea4ea` (Task 1/3 commit)

**2. [Rule 2 - Missing Critical] `mapping_to_turtle`'s non-Turtle export re-serialises from the stored Turtle rather than returning it verbatim**
- **Found during:** Task 1 (format-dispatch implementation)
- **Issue:** The existing "return `owl_turtle` verbatim when present" fast path only makes sense for `format="turtle"` requests; blindly returning it for a `format="xml"` request would silently emit Turtle text as an "RDF/XML" response.
- **Fix:** `mapping_to_turtle` now checks the resolved format: verbatim return only when `resolved_format == "turtle"`; otherwise it re-parses the inline Turtle and re-serialises into the requested format via `parse_owl_graph`.
- **Files modified:** `arango_sparql/translate/owl.py` (`mapping_to_turtle`)
- **Verification:** `test_mapping_to_turtle_xml_from_inline_owl_turtle_reserialises` asserts the RDF/XML output differs from the stored Turtle and is a valid, non-empty RDF/XML document with the same triple count.
- **Committed in:** `b1ea4ea` (Task 1/3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 2 — missing critical functionality required to keep a codebase-wide invariant intact under multi-format import/export).
**Impact on plan:** Both fixes were necessary corollaries of adding multi-format support to a bundle field whose downstream consumers hard-assume Turtle; without them, the plan's own stated goal ("RDF/XML round-trips work... reusing the existing envelope UNCHANGED") would have been violated by a silent invariant break. No scope creep — no new files, no new exception classes, no route surface beyond what the plan specified.

## Issues Encountered

None — implementation proceeded without blockers. rdflib 7.6.0's native support for all four target formats (verified directly: Turtle→RDF/XML→JSON-LD→N-Triples round-trip via `Graph.isomorphic()`) matched RESEARCH.md's Pitfall 1 findings exactly, so no dependency work was needed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The RDF/XML import/export gap that blocked Plan 04-04 (AOE own-half contract test, D-04) and Plan 04-05 (Ontology Playground roundtrip, D-06) is closed: both `/mapping/import-owl` and `/mapping/export-owl` now handle RDF/XML end-to-end with the same OwlBomb/OwlParse defences as Turtle.
- The RDF/XML billion-laughs/XXE defence (T-04-03/T-04-05 in this plan's threat model) is proven with dedicated unit + route tests, so Plan 04-05's Ontology Playground fixture (a real vendored RDF/XML document) can be imported/exported with confidence the parser is hardened against a hostile variant.
- No blockers for the next wave.

---
*Phase: 04-interoperability-performance-verification*
*Completed: 2026-07-28*

## Self-Check: PASSED

All claimed files exist and all claimed commit hashes (`b1ea4ea`, `62e6211`, `5ef78ca`) resolve in `git log`.
