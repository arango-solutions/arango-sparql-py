---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-07-23T21:33:18.401Z"
last_activity: 2026-07-23
progress:
  total_phases: 13
  completed_phases: 6
  total_plans: 30
  completed_plans: 28
  percent: 46
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-15)

**Core value:** Deterministic W3C SPARQL→AQL correctness stays sacred (never regress); NL→SPARQL quality becomes measurable and improvable.
**Current focus:** Phase 07.3 — nl-to-sparql-entity-instance-grounding

## Current Position

Phase: 07.3 (nl-to-sparql-entity-instance-grounding) — EXECUTING
Plan: 5 of 6
Status: Ready to execute
Last activity: 2026-07-23

Progress: [█████████░] 93%

## Performance Metrics

**Velocity:**

- Total plans completed: 21 (Phases 1–3 shipped pre-GSD, outside GSD tracking)
- Average duration: n/a
- Total execution time: n/a

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1–3 | shipped pre-GSD | - | - |
| 06 | 3 | - | - |
| 06.2 | 4 | - | - |
| 07 | 4 | - | - |
| 07.1 | 6 | - | - |
| 07.2 | 4 | - | - |

**Recent Trend:**

- Last 5 plans: n/a
- Trend: n/a (bootstrap)

*Updated after each plan completion*
| Phase 06 P01 | 6min | 2 tasks | 3 files |
| Phase 06 P02 | 8min | 2 tasks | 3 files |
| Phase 06 P03 | 6min | 2 tasks | 1 files |
| Phase 06.2 P01 | ~10min | 3 tasks | 2 files |
| Phase 06.2 P02 | ~15min | 3 tasks | 2 files |
| Phase 06.2 P03 | 10min | 3 tasks | 3 files |
| Phase 07 P01 | 7min | 3 tasks | 4 files |
| Phase 07 P02 | 10min | 2 tasks | 2 files |
| Phase 07 P03 | 20min | 3 tasks | 6 files |
| Phase 07 P04 | ~35min | 4 tasks | 9 files |
| Phase 07.3 P01 | 20min | 3 tasks | 6 files |
| Phase 07.3 P02 | 10min | 2 tasks | 2 files |
| Phase 07.3 P03 | 35min | 3 tasks | 5 files |
| Phase 07.3 P04 | 15min | 3 tasks | 3 files |

## Accumulated Context

### Roadmap Evolution

- Phase 06.1 inserted after Phase 6: Re-point nl2sparql onto arango-query-core shared engine (prerequisite for engine-side SOTA) (URGENT)
- Phase 06.2 inserted after Phase 6: harder corpus + genuine live-model baseline (unblocks measurable few-shot lift) (URGENT)
- Phase 07.1 inserted after Phase 7: NL→SPARQL synthetic eval-corpus growth to reach statistical power (MDE ≤ 5pt); corpus+bank only, heavy levers deferred to v1.1 (URGENT)
- Phase 07.2 inserted after Phase 7: Execution-based (answer-set) eval judging for adopted benchmarks; CK25 first, QALD later — surfaced by 07.1 live-eval finding that the canonical judge floors real LLM output at 0% (URGENT)

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Recent decisions affecting current work:

- DEC-0001: Named graphs → per-document `_graph` attribute (Accepted, NOT locked)
- DEC-0002: Cross-subject OPTIONAL LeftJoin — Option A shipped, B/C deferred (Partially resolved, NOT locked)
- Establish NL eval BEFORE tuning (Phase 6 sequenced first); port harness + few-shot from `arango-cypher` sister repo
- [Phase 06]: corpus.yml reuses bgp_select.yml's ontology prefix header (phys:collectionName) so SchemaResolver.from_turtle resolves without modification
- [Phase 06]: Deliberate near-miss case drops the age binding in its scripted response vs. gold, keeping the scripted pass-rate intentionally below 1.0
- [Phase 06]: configs.yml documents openai-gpt4o-mini as the real-provider sweep shape; CI enforces the scripted config only
- [Phase 06]: baseline.json authored from the actual run('scripted') output (5/6 pass, pass_rate=0.8333) rather than an aspirational number
- [Phase 06]: Per-case regression in test_eval.py is a hard gate, not informational only
- [Phase 06]: CI wiring (.github/workflows/ci.yml new eval job) deferred — out of 06-02's file scope
- [Phase 06]: CI eval job installs .[dev,nl,service] and runs RUN_EVAL=1 pytest -m eval; existing test job marker exclusion left unchanged
- [Phase 06]: W3C DAWG query-eval coverage confirmed unchanged at 96.4% (244/253); zero transpiler files touched by Phase 6
- [Phase 06.2-01]: `expect_refusal` pinned as the negatives marker key across corpus data, CorpusCase field, and the _judge branch
- [Phase 06.2-01]: gold-must-parse validator skips refusal cases (expected holds a human rationale, not gold SPARQL); SparqlParseError re-raised as pydantic ValueError
- [Phase 06.2-01]: _load_corpus validates every case then returns the raw dict unchanged (a load-time gate, not a data-flow rewrite)
- [Phase 06.2-01]: BaselineConfig carries optional model/temperature/corpus_sha so Plan 04 folds a live baseline in without re-touching runner.py
- [Phase 06.2-02]: :placed/:knows are dedicated edge collections (phys:edgeCollectionName), not attribute joins — a bare owl:ObjectProperty raises SchemaResolutionError, so the committed Task-1 comment was wrong and its golds could not transpile (fixed)
- [Phase 06.2-02]: property-path positives use :knows/:placed as real graph edges; transitive :knows+/:knows* use the default property_path_max_depth (10) with no knob override
- [Phase 06.2-02]: 16 positive golds added (4 OPTIONAL, 3 aggregation/GROUP BY, 9 property-path/multi-hop); every non-refusal gold proven transpilable by test_gold_transpilable.py
- [Phase 06.2]: [Phase 06.2-03]: 3 expect_refusal negatives — 2 malformed-SPARQL drift-proof triggers + unsupported !(^:knows); all refuse to empty AQL, PASS inverted judge
- [Phase 06.2]: [Phase 06.2-03]: baseline.json regenerated from true run('scripted') — 0.96 (24/25), all 25 cases tracked, near-miss=false, nested schema preserved
- [Phase 06.2]: [Phase 06.2-03]: 0<pass_rate<1 is a SENTINEL; real guard is per-case deliberate-near-miss passed is False (AI-SPEC SC2)
- [Phase 06.2-04]: README.md live-baseline runbook documents the key-gated sweep (NL2SPARQL_API_KEY, not OPENAI_API_KEY — Pitfall 1), corpus_sha capture, and the MANUAL human-reviewed fold-in into baseline.json (never auto-regenerated in CI — Pitfall 2)
- [Phase 06.2-04]: no-network structural test validates the openai-gpt4o-mini companion via BaselineConfig (model/temperature==0.1/corpus_sha + 0<pass_rate<1 headroom) and SKIPS key-free until the entry is folded in; a static guard asserts the CI gate only ever runs("scripted")
- [Phase 07-01]: DenseRetriever pinned to sentence-transformers/all-MiniLM-L6-v2 @ 7dbbc90392e2f80f3d3c277d6e90027e55de9125 (verified present on huggingface.co, matched RESEARCH candidate exactly)
- [Phase 07-01]: cached_few_shot_index() lives engine-side in arango_query_core.nl.fewshot (not adapter-side) so Cypher's future adapter shares the same memoized model cache
- [Phase 07-01]: arango-query-core bumped to commit a5a42cdc89184ebbc9896198071a4ea8f0b7aa20 (pushed to origin/main) — Plan 03 must bump arango-sparql-py's pyproject.toml git pin to this SHA
- [Phase 07-02]: 07-02: _skeleton() blanks both literal values AND quoted URIRef('...') tokens (not literal-only), verified empirically against all 22 corpus skeletons before finalizing the bank
- [Phase 07-02]: 07-02: 23-example fewshot_bank.yml (5 basic BGP, 4 OPTIONAL, 4 aggregation, 6 property-path, 4 multi-hop) authored with corpus.yml closed, ontology shared verbatim
- [Phase 07-02]: 07-02: NL-FEW-01 not marked complete yet (spans plans 01-03 per 07-01 precedent); seam-wiring lands in 07-03
- [Phase 07-03]: production seam defaults to mode=auto (D-05); Plan 04 must report the bm25 arm as the honest default-install number since dense requires .[dense]
- [Phase 07-03]: M5 origin-fetchability verified live via git ls-remote before uv lock; pin bumped to a5a42cdc89184ebbc9896198071a4ea8f0b7aa20
- [Phase 07-03]: fixed a pre-existing (pre-Phase-7) bug in test_engine_reproduces_baseline_verdicts — refusal-blind judging + stale hardcoded 0.8333 pass-rate, verified broken since 06.2 completion
- [Phase 07-04 Task 1]: OpenAICompatibleClient.generate() omits temperature for gpt-5/o1/o3/o4-family models (400 on any explicit value); gpt-5/gpt-5-mini pricing rows added to cost.py — exact rates sourced from training knowledge, not live-fetched (openai.com/pricing behind a Cloudflare challenge this session); flag for spot-check before the Task 4 sweep
- [Phase 07-04 Task 2]: configs.yml gains the additive 3-arm (zero/dense/bm25) x 3-model (gpt-4o-mini/gpt-5-mini/gpt-5) matrix; runner.run() threads few_shot config into NlPipeline via the 07-03 passthrough with a once-per-arm memoized index + D-06 isinstance(retriever, DenseRetriever) guard; BaselineConfig gains D-04 embedding provenance fields; pure-Python paired_mcnemar/bootstrap_paired_delta helpers added (no scipy) — run(config_name)->Report stays byte-identical
- [Phase 07-04 Task 3]: README.md §7 documents the redesigned N>=5, paired-McNemar-primary (p<0.05 on gpt-4o-mini anchor) sweep runbook; test_eval.py gains a no-network dense-baseline structural test (skips until folded in); tests/w3c/test_coverage_gate.py is a new COMMITTED, ASSERTING SC4 gate (QUERY_EVAL >= 96.4%, currently 96.44%) wired into a new ci.yml `w3c-coverage` job — deliberately carries no `w3c` marker so it runs off the xfail-tolerant path
- [Phase 07-04]: NL-FEW-02 closed via the plan-sanctioned human-accepted-documented-null path -- gpt-4o-mini dense-vs-zero paired McNemar returned p=0.453 (b=5,c=2), not significant at n=25's ~16pt MDE; NOT a passed confirmatory test
- [Phase 07-04]: SECONDARY bm25-vs-zero (gpt-4o-mini) IS significant (p=0.0312, +19pt) but reported as secondary/exploratory, never substituted for the confirmatory dense-vs-zero result
- [Phase 07-04]: Lexical BM25 outperformed dense embeddings in all 3 model tiers (gpt-4o-mini/gpt-5-mini/gpt-5) -- contradicts the phase's founding SOTA-survey dense-#1 thesis; documented as a genuine finding
- [Phase 07-04]: sweep results folded into baseline.json as a sibling phase07_dense_few_shot_sweep top-level key (aggregate-only) rather than configs['*-dense'] BaselineConfig entries, since only aggregate pass-rates + single-pairing McNemar were captured (not full per-case dicts) and BaselineConfig.cases is a required field
- [Phase 07-04]: resolved model snapshot ids were not captured this sweep, so the M2 dense-vs-committed-0.32 continuity check is flagged inapplicable/invalid rather than silently compared
- [Phase 07.3-01]: arango-query-core bumped locally to commit 11b71d584769108e6c3c926049e0a3f359c92037 (seam 6 grounding_index, LabelIndex/GroundedEntity) — NOT pushed, NOT pin-bumped; Plan 02 owns push + pyproject.toml pin bump
- [Phase 07.3-01]: grounding.py has zero production default/memoization; construction is fully caller-owned (no lru_cache factory), since there is no canonical grounding-data bank path the way there is for few-shot
- [Phase 07.3-01]: Label sanitization (_sanitize_label) applied at render time strips C0 control chars/newlines, collapses whitespace, caps length at 200 chars; proven no-op on clean labels (T-07.3-01 mitigation)
- [Phase 07.3-02]: arango-query-core pin bumped to 3ff0d53d0eb39aca80b4ec01a93deae7939569e9 (not the 11b71d5 recorded in 07.3-01), verified fetchable via git ls-remote refs/heads/main on both ArthurKeen and arango-solutions remotes — 11b71d5 failed mypy+ruff CI upstream; 3ff0d53 is the CI-clean fix commit both remotes now carry
- [Phase 07.3-02]: uv lock also caught up pre-existing lock staleness (mypy, ruff==0.15.22, arangodb-schema-analyzer[anthropic]) from commit c2fafe7 that was never re-locked — mechanically necessary for uv lock to succeed against current pyproject.toml; not new churn from this plan's SHA bump
- [Phase 07.3]: [Phase 07.3-03]: grounding_index() has no production-default fallback (explicit-injection-only) -- no canonical instance/entity label-data source exists yet, matching grounding.py's own design
- [Phase 07.3]: [Phase 07.3-03]: fixed a pre-existing Rule-3 regression in legacy SparqlLanguageAdapter (arango_sparql/nl2sparql/adapter.py, used by nl_to_sparql) -- the 07.3-02 pin bump made seam 6 mandatory in QueryLanguageAdapter, breaking that adapter with AttributeError (3 pre-existing test_adapter.py failures, verified broken at 07.3-02 HEAD before Plan 03 started); fixed with the same seam 6 impl mirrored from engine_adapter.SparqlAdapter
- [Phase 07.3-04]: build_label_index expands prefixed label_predicates (rdfs:/pv:) against a small hardcoded prefix map, not a parsed PREFIX preamble — CK25's prefixes are fixed; keeps the builder self-contained and dependency-free of ontology-text parsing
- [Phase 07.3-04]: Measured gold-IRI retrieval recall = 24/25 = 0.96, exactly matching the spike; recall guard runs in the always-on pytest tier (no RUN_EVAL) — Provides deterministic offline CI evidence for NL-ACC-01 independent of the human-run live sweep

### Pending Todos

- Minor cleanup: legacy `arango_sparql/nl2sparql/_core.py::nl_to_sparql` is a stub returning a comment; real path is `NlPipeline`.

### Blockers/Concerns

- [Phase 06.2-04] AWAITING HUMAN CHECKPOINT (Task 2, checkpoint:human-action): the credentialed live `openai-gpt4o-mini` sweep needs a real `NL2SPARQL_API_KEY` the agent must never hold. Human runs `RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "from tests.nl2sparql.eval.runner import run, write_report; r=run('openai-gpt4o-mini'); write_report(r); print('pass_rate', r.pass_rate); [print(c.name, c.passed) for c in r.cases]"` + `git log -1 --format=%h -- tests/nl2sparql/eval/corpus.yml`, confirms headroom (pass_rate < 1.0), and pastes back aggregate + per-case verdicts + corpus_sha. Then the continuation folds them into baseline.json (Task 3 fold-in) and writes 06.2-04-SUMMARY.md.
- [Phase 5] WP-UI-CAT / WP-UI-TENANT / WP-UI-CORR are backend-blocked (need async introspect, tenant catalogue, translator source-map).
- [Gate] W3C DAWG query-eval coverage must stay ≥ 96.4% throughout the NL workstream (Phases 6–7).
- [Dep] Upstream hard dependency `arangodb-schema-analyzer` pinned ≥0.6.1,<0.7.0.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Federation | SPARQL `SERVICE` / federated query | v2 | bootstrap |
| OPTIONAL | DEC-0002 Options B/C (doc-emulation + multi-model) | v2 (travels with federation) | bootstrap |
| Write path | SPARQL 1.1 Update | Out of scope (405) | bootstrap |

## Session Continuity

Last session: 2026-07-23T21:33:18.395Z
Stopped at: Completed 07.3-04-PLAN.md (eval-only grounding index builder + recall/default guards)
Resume file: None
