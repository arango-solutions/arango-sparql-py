# Phase 4: Interoperability & performance verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-27
**Phase:** 4-interoperability-performance-verification
**Areas discussed:** Foxx parity, AOE roundtrip, Third-party tool depth, Perf enforcement posture

**Framing note:** Discussion opened by surfacing that three of the four Phase 4
counterparties (legacy Foxx service + fixtures, AOE, cypher-py sister) are
**absent from the workspace** — `references/` symlinks are dead (only
`references/README.md` exists; no sibling repos in `~/dev`). The user added an
unprompted steer during area selection: **"Foxx is deprecated."** After the
first fork presentation the user asked for plain-language elaboration on all
four before deciding; elaboration was provided, then the forks re-presented.

---

## Foxx parity (REQ-foxx-parity)

| Option | Description | Selected |
|--------|-------------|----------|
| Descope w/ ADR waiver | ADR records Foxx deprecation → parity no longer a v1.0 gate; strike roadmap SC1; no harness; W3C already guards correctness | ✓ |
| Lightweight golden proof | Vendor legacy SPARQL fixture queries; assert semantically-equivalent AQL via goldens + pyoxigraph; no live Foxx | |
| Live Docker roundtrip | Stand up deprecated Foxx + us in docker-compose, replay fixtures, compare bindings (§13.4 as written) | |

**User's choice:** Descope w/ ADR waiver
**Notes:** User explicitly flagged "Foxx is deprecated" as the reason. The legacy
`arango-sparql` JS Foxx service is what this project rewrote; validating against
a dying reference adds little given the W3C DAWG suite (96.4%) already proves
SPARQL→AQL correctness independently.

---

## AOE roundtrip (REQ-ontoextract-integration)

| Option | Description | Selected |
|--------|-------------|----------|
| Test our half only | No live AOE; assert /mapping/export-owl → import-owl triple-bag equality + ASK/SELECT via /sparql on Docker ArangoDB | ✓ |
| Recorded-fixture contract | Capture one real AOE-exported OWL bundle as a fixture; test our import→re-export against it | |
| Full two-service Docker | Clone + run AOE alongside us, drive the real Q7 flow end-to-end | |

**User's choice:** Test our half only
**Notes:** Elaboration clarified that §12.2's AOE integration is "one env var"
on AOE's side — the testable substance is our own `/mapping` import/export OWL
fidelity, not the external service.

---

## Third-party tool depth (REQ-thirdparty-tool-compat)

| Option | Description | Selected |
|--------|-------------|----------|
| Auto light, doc heavy | Automate SPARQLWrapper (Python) + Ontology Playground roundtrip (file-based); Protégé/arq + YASGUI documented + recorded transcript | ✓ |
| Automate all incl. JVM | Add JVM+Jena arq Docker image to drive Protégé headless, plus the two light ones | |
| All documented-manual | No automated tool tests; how-to recipes + hand-verified checkmarks only | |

**User's choice:** Auto light, doc heavy
**Notes:** Matches §13.1's nightly/on-demand posture. Playground is file-based
(exercises our /mapping routes — no browser needed); SPARQLWrapper is pure
Python. Protégé (JVM/arq) and YASGUI (browser) are too heavy to justify a CI
image for a verification phase.

---

## Perf enforcement posture (REQ-performance-slos)

| Option | Description | Selected |
|--------|-------------|----------|
| Tiered: gate cheap, report rest | CI-block fast in-process rows (translate cold/warm, execute overhead); Docker/LLM/memory/concurrency → local LATENCY_REPORT.md, reported not gated | ✓ |
| Full CI gate all 11 rows | Enforce every §9.4 budget as per-PR blocking, incl. live-LLM + Docker rows | |
| All local-artifact only | No CI perf gating; whole suite is a nightly/on-demand artifact | |

**User's choice:** Tiered: gate cheap, report rest
**Notes:** Shared GitHub runners jitter (flaky p95); `/nl-translate` needs a
live LLM key that never goes in CI; memory/concurrency rows need Docker. Gate
only the deterministic in-process rows; report the rest.

---

## Claude's Discretion

- Perf baseline capture/storage mechanics (how stable p95 numbers are measured
  and checked in) within the tiered posture.
- The exact OWL source fixture for the AOE roundtrip.
- Test file layout, and `arq`/how-to recipe wording.

## Deferred Ideas

- Live Foxx roundtrip (§13.4) — rejected outright (Foxx deprecated), not deferred.
- Full two-service AOE Docker roundtrip — deferred; revisit only on a real
  integration regression the own-half test can't catch.
- Automated Protégé (JVM/arq) + YASGUI (browser) CI smoke — deferred; documented
  + recorded transcript for now.
- Full per-PR CI gating of all 11 §9.4 perf rows — deferred until a stable
  dedicated perf runner exists.
