---
phase: 4
slug: interoperability-performance-verification
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-27
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from `04-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` (only runner per `.cursor/rules/200-testing.mdc`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — needs a new `perf` marker this phase |
| **Quick run command** | `pytest -m "not integration and not w3c and not eval and not perf" --tb=short -q` |
| **Full suite command** | `RUN_INTEGRATION=1 pytest tests/integration tests/cross tests/perf --tb=short -q` |
| **Estimated runtime** | ~30s quick; integration/perf gated on Docker + `RUN_INTEGRATION=1` |

---

## Sampling Rate

- **After every task commit:** Run `pytest -m "not integration and not w3c and not eval and not perf" -q` (existing fast default; unaffected by this phase's additions)
- **After every plan wave:** Run `RUN_INTEGRATION=1 pytest tests/integration tests/perf -q` plus a manual run of the two `docs/howto/` recorded-transcript recipes
- **Before `/gsd-verify-work`:** `pytest tests/perf -m perf -k "translate_latency or execute_overhead"` green (CI-blocking); the 8 report-only rows produce a fresh `LATENCY_REPORT.md` reviewed by a human, not gated
- **Max feedback latency:** ~30s (quick default)

---

## Per-Task Verification Map

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| REQ-foxx-parity | ADR + plan-of-record amendment only, no test | n/a (documentation) | n/a — PRD/ROADMAP/REQUIREMENTS.md edits | n/a |
| REQ-thirdparty-tool-compat (SPARQLWrapper) | SELECT + ASK + Service Description over a real bound HTTP server | integration | `RUN_INTEGRATION=1 pytest tests/integration/test_sparqlwrapper_smoke.py -m integration -q` | ❌ Wave 0 |
| REQ-thirdparty-tool-compat (Ontology Playground) | File-based OWL export→import→re-export→isomorphic | integration | `RUN_INTEGRATION=1 pytest tests/integration/test_ontology_playground_roundtrip.py -m integration -q` | ❌ Wave 0 |
| REQ-thirdparty-tool-compat (Protégé, YASGUI) | Documented-manual recorded transcript | manual-only (D-07, no CI image) | n/a | ❌ Wave 0 (`docs/howto/`) |
| REQ-ontoextract-integration | export-owl → import-owl isomorphism + ASK/SELECT via `/sparql` | integration | `RUN_INTEGRATION=1 pytest tests/integration/test_aoe_roundtrip.py -m integration -q` | ❌ Wave 0 |
| REQ-performance-slos (3 CI-gated rows) | p95 within 25% of baseline, in-process | perf (new marker) | `pytest tests/perf/test_translate_latency.py tests/perf/test_execute_overhead.py -m perf -q` | ❌ Wave 0 |
| REQ-performance-slos (8 report-only rows) | p95/memory/concurrency measured → `LATENCY_REPORT.md`, never gates | perf (non-blocking) / manual for `/nl-translate` | `RUN_INTEGRATION=1 pytest tests/perf -m perf -k "not translate_latency and not execute_overhead" -q` | ❌ Wave 0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — register the `perf` marker; add `SPARQLWrapper` as a test/dev dependency
- [ ] `tests/perf/__init__.py` + `tests/perf/conftest.py` — new directory, no existing scaffolding
- [ ] `tests/perf/baseline.json` — first-run capture, checked in after human review (mirrors `tests/nl2sparql/eval/baseline.json`)
- [ ] `tests/fixtures/cosmic_coffee.rdf` — vendor the MIT fixture with a provenance note (mirrors `tests/nl2sparql/eval/vendored/*/NOTICE.md`)
- [ ] `docs/howto/` — directory does not exist yet
- [ ] RDF/XML format-plumbing fix in `arango_sparql/translate/owl.py` + `arango_sparql/service/routes/mapping.py` — blocks the RDF/XML row of both the AOE and Ontology Playground tests

*No existing test infrastructure covers any of Phase 4's requirements — from-scratch build within an otherwise mature suite.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Protégé smoke (SELECT + ASK + Service Description) | REQ-thirdparty-tool-compat | JVM desktop; no CI image (D-07) | `docs/howto/` recipe driving Apache Jena `rsparql --service <our /sparql> --query <q>`; capture recorded transcript |
| YASGUI smoke (SELECT + ASK + Service Description) | REQ-thirdparty-tool-compat | Browser widget; no CI image (D-07) | `docs/howto/` recipe with recorded transcript against running service |
| `/nl-translate` latency row | REQ-performance-slos | Live LLM; key never in CI | Local/on-demand run → `LATENCY_REPORT.md` |
| 8 report-only perf rows | REQ-performance-slos | Docker/noisy/LLM; advisory not gated (D-09) | Local run → checked-in `LATENCY_REPORT.md`, human-reviewed |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-27 (plan-checker VERIFICATION PASSED — Dimension 8 green)
