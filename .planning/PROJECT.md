# arango-sparql-py

## What This Is

A Python-native SPARQL 1.1 → ArangoDB AQL transpiler, packaged as both a library
and a W3C SPARQL 1.1 Protocol FastAPI microservice, with a natural-language →
SPARQL pipeline layered on top (Anthropic/OpenAI backends). It replaces the legacy
JS Foxx `arango-sparql` service, adapts to PG/LPG/RPT/hybrid physical schemas, and
mirrors its sister project `arango-cypher-py`. Targets Python 3.11/3.12 and
ArangoDB 3.11/3.12.

## Core Value

Deterministic, W3C-grounded SPARQL→AQL correctness is sacred (never regress the
transpiler), while making NL→SPARQL translation quality **measurable and
improvable** so the natural-language layer can be tuned with confidence.

## Requirements

### Validated

<!-- Shipped and confirmed valuable (mature repo — pre-GSD). -->

- ✓ SPARQL 1.1 → AQL transpiler core; W3C DAWG query-eval coverage at 96.4% — Phase 1
- ✓ Physical-model coverage (PG/LPG/RPT/DOCUMENT + hybrids + edge styles) — Phase 1
- ✓ Single-AQL hybrid BGP translation joined on subject URI — Phase 1
- ✓ Dual schema detection (heuristic + analyzer-backed, analyzer wins on auto) — Phase 1
- ✓ W3C SPARQL 1.1 Protocol endpoint (GET/POST /sparql, accept negotiation, error contract, Service Description) — Phase 2
- ✓ 9-route schema/mapping HTTP surface (cypher-py parity) — Phase 2
- ✓ Operational parity (session/connect/public-mode/CORS/rate-limit/SSRF/redaction/startup-guard) — Phase 3
- ✓ STRIDE threat-model mitigations + privacy (no-bodies-in-logs, JSON log envelope) — Phase 3
- ✓ Config-appendix normativity gate — Phase 3
- ✓ NL→SPARQL pipeline machinery (NlPipeline, PromptBuilder, RepairLoop, providers, cost/models) — pre-existing, feeds Phases 6–7
- ✓ NL→SPARQL eval harness + seed corpus; checked-in `baseline.json` regression gate; scripted pass-rate now a tracked metric (0.833, 5/6) — Phase 6
- ✓ NL→SPARQL eval corpus grown by *adopting* public benchmarks (not synthesizing): QALD-9-plus (514 golds, CC-BY-4.0) as the powered capability gate (achieved MDE ~0.055–0.062), CK25 (49 golds, CC-BY-4.0) as the corporate-domain anchor, + a 12-case `expect_refusal` supplement; per-set baselines reported SEPARATELY (never blended) with achieved-MDE; power-analysis module salvaged; transpiler untouched, W3C ≥ 96.4% held (NL-BENCH-01..07) — Phase 07.1
- ✓ Execution-based (answer-set) eval judging for adopted benchmarks: opt-in `judge: execution` runs gold + candidate SPARQL through pyoxigraph and compares ANSWERS up to variable renaming + IRI↔label normalization (SELECT + ASK), with distinct D-05 engine-reject buckets; full CK25 instance graph vendored (951,747 B / 26,903 triples, CC-BY-4.0, provenance-guarded); `scripted-ck25` gold-vs-gold sanity gate green at 100%; CK25's first real execution-graded live number recorded as the reported-not-gated anchor (`openai-gpt4o-mini-ck25` = 12.2%, 6/49); scripted canonical CI default + W3C ≥ 96.4% (96.44%) untouched (NL-EVAL-05) — Phase 07.2

### Active

<!-- Current scope. Building toward these. NL workstream is the immediate goal. -->

- [ ] **NL→SPARQL few-shot index** (Phase 7 — NEXT): BM25 few-shot (≤3 shots) feeding `PromptBuilder.few_shot_examples`; prove pass-rate lift via the harness
- [ ] **Interoperability & performance verification** (Phase 4): Foxx roundtrip, third-party tool compat, ontoextract roundtrip, perf SLOs (Docker/live-gated)
- [ ] **UI workbench parity completion** (Phase 5): Playwright/a11y CI harness + 3 backend-blocked WPs (UI-CAT, UI-TENANT, UI-CORR)
- [ ] **Public release readiness** (Phase 8): repo public, green CI matrix, license/docs/runbook, SBOM on v1.0 tag

### Out of Scope

<!-- Explicit v1 exclusions with reasoning. -->

- SPARQL 1.1 Update (INSERT/DELETE/LOAD/CLEAR/CREATE/DROP/COPY/MOVE/ADD) — writes go through AQL directly; returns 405
- Federated query (`SERVICE`) — deferred to possible v2; Service Description advertises no `sd:BasicFederatedQuery` (dominant W3C XFAIL bucket, consciously accepted)
- Inferencing/reasoning (RDFS/OWL entailment) — ontology is mapping metadata, not a reasoning surface
- Multi-tenancy across separate processes — sessions are per-process in-memory; needs sticky-session LB
- Replacing AQL — this is a transpiler, not a competing engine
- Asking the LLM for AQL directly — forbidden by rule-300; LLM emits SPARQL only, transpiler emits AQL

## Context

- **Mature brownfield repo.** Transpiler, FastAPI service, and UI shell already ship
  (see `tests/w3c/COVERAGE_REPORT.md`, `docs/architecture/implementation_plan.md`).
  W3C DAWG query-eval coverage is 96.4% (244/253 pass, 9 XFAIL; top XFAILs are
  deferred SERVICE/federation cases). Syntax positive 100%.
- **NL pipeline is real and complete** — `NlPipeline` (prompt→LLM→deterministic
  translate→bounded repair loop→`PipelineOutcome`), `PromptBuilder` (Turtle-ontology
  system prompt), `RepairLoop`, `client.py` (OpenAI/Anthropic/Scripted), `cost.py`,
  `models.py`, `samples.py`. The GAPS are the eval harness and few-shot only.
- **Eval harness is stubbed today:** `tests/nl2sparql/eval/runner.py::run()` and
  `write_report()` both raise `NotImplementedError`; `corpus.yml`/`configs.yml` absent;
  no `baseline.json`. Port/adapt from sister repo `arango-solutions/arango-cypher`'s
  proven nl2cypher eval harness (cited at 93–100%).
- **Few-shot is absent:** `arango_sparql/nl2sparql/fewshot.py` does not exist; the
  `PromptBuilder.few_shot_examples` seam is wired but empty.
- **Near-term cleanup (minor):** legacy `arango_sparql/nl2sparql/_core.py::nl_to_sparql`
  is a stub returning a comment; the real path is `NlPipeline`.
- **Cross-project ties:** upstream hard dep `arangodb-schema-analyzer` (≥0.6.1,<0.7.0);
  downstream consumer `arango-ontoextract`; parity/shared-substrate sister `arango-cypher-py`.

## Constraints

- **Tech stack**: Python 3.11/3.12 library + FastAPI microservice; Anthropic/OpenAI LLM backends for the NL layer.
- **NL module layout (rule-300)**: `arango_sparql/nl2sparql/**` must mirror `arango_cypher/nl2cypher/` — `_core.py`, `providers.py`, `fewshot.py`, `tenant_guardrail.py`, `tenant_scope.py`, `entity_resolution.py`, `_aql.py`.
- **NL API contract (rule-300)**: `NL2SparqlResult` must match `NL2CypherResult` field-for-field (sparql, explanation, confidence, method, schema_context, token counts, retries) for cross-repo telemetry.
- **NL prompt (rule-300)**: always supply the OWL ontology in Turtle; pin `SPARQL 1.1`, forbid vendor extensions, require fully-qualified IRIs, fenced ```sparql``` output.
- **Few-shot budget (rule-300)**: BM25 index over a curated YAML corpus; never inline more than 3 shots.
- **Corrections store (rule-300)**: `nl_corrections.db` (SQLite, WAL), identical schema to Cypher; correction lookup before any LLM call.
- **Forbidden (rule-300)**: never ask the LLM for AQL; never inline the whole OWL when a tenant-scoped slice suffices.
- **Transpiler porting (skill)**: SPARQL→AQL semantics must match legacy Foxx `references/arango-sparql/src/lib/`; parameterized builder only (no string-concat AQL, no inlined literals); golden + pyoxigraph cross-validation per node. No ANTLR/custom parsers.
- **No-regression gate**: W3C DAWG query-eval coverage must stay ≥ 96.4% throughout the NL workstream.
- **Upstream dependency**: `arangodb-schema-analyzer` ≥0.6.1,<0.7.0 (first-class, not optional).

## Key Decisions

<!-- DEC-0001 / DEC-0002 recorded per intel; NON-LOCKED (not GSD-locked). -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| DEC-0001: Named graphs → per-document `_graph` attribute (Accepted 2026-05-20, **not locked**) | Layout-agnostic across PG/LPG/RPT; A→B stays possible, avoids O(N) UNION explosion of per-collection membership | ⚠️ Revisit — ~+4.4pp W3C reachable; default-graph defaults to lax |
| DEC-0002: Cross-subject OPTIONAL (LeftJoin) emitter (Partially resolved 2026-06-02, **not locked**) | RPT-native left-join (Option A) shipped + OPTIONAL-rebind-in-MINUS resolved; Options B/C deferred with federation slice | ⚠️ Revisit — moved W3C 95.7%→96.4%; remaining branches raise structured `UnsupportedSparqlError` |
| Establish NL eval before tuning (Phase 6 first) | Cannot improve NL quality without a measurable, checked-in baseline gate | ✓ Delivered (Phase 6) — `baseline.json` gate, scripted pass-rate 0.833 (5/6), rdflib canonical-algebra judge, CI `eval` job |
| Port eval harness + few-shot from `arango-cypher` sister repo | Proven at 93–100%; parity keeps cross-repo telemetry aligned | ⚠️ Adapted, not ported — `references/` symlinks are unreachable on this machine; Phase 6 harness was built grounded in this repo's own shipped code (docstring = spec) |

---
*Last updated: 2026-07-27 after Phase 07.4 completion (predicate/schema-convention grounding, seam 7). NL-ACC-02 closed via the documented-null path on a valid execution-graded experiment: predicate/schema-convention grounding shows no CK25 lift (additive entity+predicate 10/49 vs entity-only 12/49, McNemar p=0.6875; predicate-alone 7/49). Entity grounding (seam 6) remains the sole confirmed CK25 lever. Follow-up: selective predicate surfacing rather than full-dump/token-match.*
