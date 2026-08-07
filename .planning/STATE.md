---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 07.5
current_phase_name: nl-sparql-query-first-synthetic-few-shot-bank
status: complete
stopped_at: Completed 07.5-06-PLAN.md (Stage-2 engine promotion shipped; synthbank seam pushed to both remotes, pin bumped 3438305). Phase 07.5 COMPLETE (6/6).
last_updated: "2026-08-07T15:11:07.548Z"
last_activity: 2026-08-05
progress:
  total_phases: 11
  completed_phases: 10
  total_plans: 49
  completed_plans: 49
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-15)

**Core value:** Deterministic W3C SPARQL→AQL correctness stays sacred (never regress); NL→SPARQL quality becomes measurable and improvable.
**Current focus:** Phase 07.5 — nl-sparql-query-first-synthetic-few-shot-bank

## Current Position

Phase: 07.5 (nl-sparql-query-first-synthetic-few-shot-bank) — COMPLETE
Plan: 6 of 6 — all complete
Status: 07.5-06 COMPLETE. Stage-2 engine promotion shipped: pure query-shape template catalog promoted to arango_query_core.nl.synthbank (engine commit 3438305, pushed to both remotes), pin bumped b669320->3438305, bank_generator.py refactored into a thin eval-side shim. NL-GEN-01 closed (ADOPT, Plan 05). Phase 07.5 COMPLETE.
Last activity: 2026-08-05

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 41 (Phases 1–3 shipped pre-GSD, outside GSD tracking)
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
| 07.3 | 6 | - | - |
| 07.4 | 6 | - | - |
| 04 | 8 | - | - |

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
| Phase 07.3 P05 | 12min | 2 tasks | 2 files |
| Phase 07.3 P06 | 25min | 3 tasks | 3 files |
| Phase 07.4 P02 | 35min | 2 tasks | 5 files |
| Phase 07.4 P03 | 25min | 3 tasks | 3 files |
| Phase 07.4 P04 | 20min | 3 tasks | 6 files |
| Phase 07.4 P05 | 20min | 3 tasks | 3 files |
| Phase 07.4 P06 | 32min | 4 tasks | 9 files |
| Phase 07.4 P06-refold | ~15min | 1 tasks | 3 files |
| Phase 04 P01 | 10min | 3 tasks | 7 files |
| Phase 04 P02 | 18min | 3 tasks | 4 files |
| Phase 04 P03 | 10min | 2 tasks | 4 files |
| Phase 04 P04 | 25min | 2 tasks | 1 files |
| Phase 04 P05 | ~20min | 2 tasks | 2 files |
| Phase 04 P06 | 45min | 2 tasks | 3 files |
| Phase 04 P07 | 55min | 1 tasks | 9 files |
| Phase 04 P08 | 5min | 1 tasks | 2 files |
| Phase 07.5 P01 | 15min | 3 tasks | 4 files |
| Phase 07.5 P02 | 32min | 2 tasks | 4 files |
| Phase 07.5 P03 | 25min | 2 tasks | 3 files |
| Phase 07.5 P04 | ~12min | 2 tasks | 3 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 07.5 P05 | 40min | 3 tasks | 3 files |

## Accumulated Context

### Roadmap Evolution

- Phase 06.1 inserted after Phase 6: Re-point nl2sparql onto arango-query-core shared engine (prerequisite for engine-side SOTA) (URGENT)
- Phase 06.2 inserted after Phase 6: harder corpus + genuine live-model baseline (unblocks measurable few-shot lift) (URGENT)
- Phase 07.1 inserted after Phase 7: NL→SPARQL synthetic eval-corpus growth to reach statistical power (MDE ≤ 5pt); corpus+bank only, heavy levers deferred to v1.1 (URGENT)
- Phase 07.2 inserted after Phase 7: Execution-based (answer-set) eval judging for adopted benchmarks; CK25 first, QALD later — surfaced by 07.1 live-eval finding that the canonical judge floors real LLM output at 0% (URGENT)
- Phase 07.4 inserted after Phase 7: NL→SPARQL predicate/schema-convention grounding — next grounding lever after 07.3 entity grounding, targeting the 17 convention-bound CK25 failures (URGENT)
- Phase 07.6 inserted after Phase 7: NL→SPARQL relationship-path grounding (seam-8): retrieve the specific TBox path connecting the question's anchor class (seam-6) to its target; targets the 16 empty-result right-entity-wrong-path CK25 failures. Step-0 recall spike GREEN (12/16 -> ~16/16 with subclass-aware nodes + inverse edges). Scope: .planning/research/relationship-path-grounding-scope.md (URGENT)

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
- [Phase 07.3-05]: grounding_cfg guarded on grounding_cfg AND data_ttl (not grounding_cfg alone) so a grounding: block with no corpus-level data_path stays a safe no-op
- [Phase 07.3-05]: build_label_index imported function-locally inside the guarded branch, keeping pyoxigraph off runner.py's module import path
- [Phase 07.3-05]: scripted-ck25-grounded verified green as a plumbing gate (pass_rate 1.0, 49/49) under RUN_EVAL=1 -- config -> build_label_index -> seam 6 -> prompt -> execution judge does not crash; explicitly documented as plumbing evidence, not accuracy evidence
- [Phase 07.3-06]: NL-ACC-01 closed via the SIGNIFICANT-LIFT path (not documented-null) -- credentialed live grounded-vs-fresh-same-session-zero CK25 sweep: 14/49 (0.2857) vs 5/49 (0.1020), McNemar b=9/c=0/p=0.0039, bootstrap delta+0.1837 CI[0.0816,0.3061], zero regressions, temperature=0.1, corpus_sha=814d227 -- stronger than the pre-planning spike (6/49->12/49, p=0.031)
- [Phase 07.3-06]: baseline.json's new openai-gpt4o-mini-ck25-grounded entry is kept fully separate from the existing openai-gpt4o-mini-ck25 entry (a stale prior-session 07.2-04 number, 6/49); the confirmatory McNemar pairing uses only the fresh same-session zero arm run this checkpoint, never the committed historical entry
- [Phase 07.4-02]: TYPE_CHECKING-guarded PredicateIndex import in both adapters + pipeline (not an unconditional top-level import) so Task 1 genuinely loads and passes tests against the still-old c6ae5e1 pin — A plain top-level import would raise ImportError at Task 1's commit since PredicateIndex does not exist until the seam-7 SHA; this is a stronger fulfillment of the plan's own harmless-against-the-still-old-pin requirement
- [Phase 07.4-02]: PredicateIndex has no public len/count; D-01 dump-vs-retrieve threshold reads the total off the private _predicates list in both adapters — The pushed seam-7 API (8adc0de) has no public accessor and this plan is in-repo-only, so no cross-repo edit was permitted to add one
- [Phase 07.4-02]: NL-ACC-02 not marked complete this plan — Mirrors NL-ACC-01/07.3-02 precedent -- this plan lands plumbing only (both adapters + pipeline conformant, pin bumped); the statistically-significant CK25 lift is unproven until the Plan 05 live sweep
- [Phase 07.4-03]: Label fallback to IRI local name when rdfs:label is absent -- keeps every GroundedPredicate/child usable for shape-detail rendering on a TBox omitting rdfs:label entirely (QALD's dbpedia_subset.ttl)
- [Phase 07.4-03]: Undeclared rdfs:range on an object property degrades to the corrected rule's own zero-children branch (category_instance), not a distinct 4th case or a crash -- mechanically consistent, and exactly matches RESEARCH.md OQ1's anticipated honest QALD finding (0 value_object, 88 category_instance, n=250)
- [Phase 07.4-03]: Predicate-count assertions read PredicateIndex._predicates directly rather than idx.retrieve('', k) -- the shared token-substring scorer always returns empty for an empty question string (verified empirically), so the plan's own literal verify-command text is unsatisfiable regardless of implementation; mirrors the 07.4-02 no-public-len/count precedent
- [Phase 07.4-04]: predicate_grounding gate reads if predicate_cfg and shared_ontology (not data_ttl) -- QALD-9-plus has no data_path, so gating on data_ttl would silently no-op the QALD predicate-grounded config forever
- [Phase 07.4-04]: predicate-recall guard measured 78/158=0.49 gold pv: mention recall (lower than the entity guard's 0.96 because the literal regex also counts class mentions a predicate-only index can never retrieve); floor asserted at 0.45, below the measured value
- [Phase 07.4-04]: scripted-ck25-predicate-grounded / scripted-qald9plus-predicate-grounded are plumbing gates only (pass_rate 1.0 because the scripted client replays each case's own gold answer), not accuracy evidence; NL-ACC-02 stays open until the Plan 05 live sweep
- [Phase 07.4-05]: Standalone predicate-alone CK25 arm (full per-case verdicts) recorded as a real configs.* BaselineConfig entry; additive arm + both QALD arms (aggregate-only) folded into a new phase07_4_predicate_grounding_sweep sibling key mirroring phase07_dense_few_shot_sweep -- avoids fabricating a cases map
- [Phase 07.4-05]: NL-ACC-02 closed via the documented-null path (NL-FEW-02 precedent): seam-7 predicate grounding regresses standalone (5/49 vs fresh 12/49 entity-alone, p=0.0156 wrong direction) and is a statistical wash additively composed on entity grounding (13/49 vs fresh 13/49, p=1.0, delta=0.0) -- no CK25 lift proven either way, never reframed as a pass
- [Phase 07.4-06]: arango-query-core PredicateIndex gains a real dump=True kwarg (upstream b669320, pushed to both remotes) -- widening k to total predicates alone never bypassed the shared scorer's zero-hit filter, so CK25 dump mode never actually dumped the full schema (CR-01 code-review BLOCKER)
- [Phase 07.4-06 re-fold]: NL-ACC-02 re-closed as a VALID documented-null (provisional/confounded caveat removed) after the credentialed human RE-RAN the CK25 predicate-grounding sweep on the fixed dump mode (pin b66932046a102898e8fff205a7ddcbedfb2c896e): standalone predicate-alone 7/49 vs a fresh 12/49 entity-alone arm (p=0.1250, non-significant -- softened from the confounded run's wrong-direction-significant p=0.0156); additive (the phase's actual composition) 10/49 vs the same fresh 12/49 arm (p=0.6875, non-significant wash, 2 real wins on ck25-8/ck25-11 offset by 4 distraction losses). Overall disposition (fails hard gate, closes via documented-null) is unchanged from 07.4-05's conclusion -- only its confounded status is resolved. baseline.json's confounded 07.4-05 CK25 entries are overwritten (superseded, not deleted-in-place) with these clean numbers.
- [Phase 04-01]: conftest.py imports (does not copy) _FakeArangoClient/_FakeDb/_FakeCursor/fake_client_factory/_connect_session from tests.test_service_sparql_routes -- the import path resolves cleanly, so no ~140-line duplication was needed
- [Phase 04-01]: cosmic_coffee.rdf pinned to commit 9a0eb93cef978b1ee6c4a6857dc0ce2733444ea0 (last commit touching that path on main), MIT license verified via GitHub API repo endpoint
- [Phase 04-02]: owl.py's owl_turtle field is re-serialised to canonical Turtle on non-Turtle import (format=xml/json-ld/nt) — Preserves the codebase-wide invariant that owl_turtle is always Turtle text (resolver.py, schema routes); storing raw non-Turtle input would have silently broken those consumers
- [Phase 04-02]: parse_owl_graph() centralizes the RDF/XML pre-parse DOCTYPE/ENTITY guard (billion-laughs/XXE) — Both the import parse and the export route's triple-count roundtrip reparse inherit the guard automatically rather than duplicating it at each call site
- [Phase 04-03]: REQ-foxx-parity retired (not built) per locked D-01/D-02: legacy Foxx is deprecated, W3C DAWG (>=96.4%) is the sole correctness gate going forward
- [Phase 04-03]: PRD Appendix B.3 mirrors the B.2 header shape (Status/Date/Owner/Related) plus Context/Decision/Considered alternatives/Consequences, matching the established ADR convention
- [Phase 04-03]: Sec 9.4's 11 SLO rows kept intact (no deletions); each annotated CI-blocking (3 fast in-process rows) or Report-only (8 Docker/LLM/noisy rows) per D-08/D-09
- [Phase 04-03]: ROADMAP SC1 kept as a struck-through historical entry (no prior struck-criterion precedent found in ROADMAP.md to follow instead)
- [Phase 04-04]: SchemaCache.put(db_name, bundle) direct injection deterministically activates an imported OWL mapping for /sparql, bypassing heuristic/analyzer auto-detection -- import-owl/export-owl are stateless (operate on request body only)
- [Phase 04-04]: AOE roundtrip fixture uses a distinct collection/namespace (AoePerson, example.org/aoe#) from test_execute_endpoint.py's Person fixture so seeded data and the process-wide SchemaCache entry never collide across sibling integration files in the same RUN_INTEGRATION=1 session
- [Phase 04-05]: SPARQLWrapper smoke test's /connect call runs over the real bound socket via urllib (not in-process), keeping the file's own no-in-process-transport invariant self-enforcing
- [Phase 04-05]: Ontology Playground roundtrip reuses SchemaCache.put() direct injection (04-04 AOE pattern) and the mapping wire-dict import/export path (not ontology_ttl) for full-fidelity isomorphism against cosmic_coffee.rdf's general catalogue triples
- [Phase 04-06]: translate_cold/translate_warm distinguished at the request-payload level (distinct-per-iteration vs reused ontology+query), not via a resolver-level cache -- none exists yet in the route layer
- [Phase 04-06]: test_execute_overhead.py clears OPENAI_API_KEY/ANTHROPIC_API_KEY/OPENROUTER_API_KEY/LLM_PROVIDER/SCHEMA_ANALYZER_PROVIDER for the duration of the test so the analyzer-enrichment path never risks a live LLM call regardless of the host's ambient .env
- [Phase 04-06]: Both perf test files suppress per-request INFO logging and defer GC (gc.collect+gc.disable) during the measurement loop -- logging I/O and mid-loop GC passes were destabilizing the p95 gate with noise unrelated to the measured work
- [Phase 04-06]: baseline.json committed with captured_env=local as the plan-sanctioned interim bootstrap; authoritative CI-captured baseline is a required follow-up (CI runs are advisory-only against this baseline until then)
- [Phase 04]: Locked ARANGO_URL/ARANGO_TEST_DB env defaults before tests/perf/conftest.py's eager import chain to close a real .env-pollution race that made Docker-gated perf rows target the wrong port/database — This repo's dev .env silently overrides ARANGO_URL to the wrong port and ARANGO_DB to the forbidden _system via load_dotenv(), triggered transitively before tests.integration.conftest resolved its own defaults
- [Phase 04]: Swapped test_concurrency.py's pinned ASK query for a SELECT after discovering /execute cannot represent ASK's boolean AQL result against a real ArangoDB — ASK translates to RETURN LENGTH(...) > 0 (scalar boolean), incompatible with SparqlExecuteResponse.bindings: list[dict]; deferred as a Known Gap rather than changing the API contract
- [Phase 04-08]: Protégé/YASGUI recorded transcripts closed via operator CLOSE WITH PLACEHOLDERS decision -- recipes are the delivered documented-manual artifact (D-07); transcripts deferred to deferred-items.md, never fabricated
- [Phase 07.5-01]: optional_relation probes the domain class via an EXACT rdf:type match (no subclass walk) -- mirrors build_predicate_index's own domain-exact-match discipline; on CK25 pv:country (domain Supplier) is a genuine positive (227 with/23 without) and pv:hasManager (domain Employee, all 47 have one) is a genuine negative, empirically verified via direct oxi_query probes before writing tests
- [Phase 07.5-01]: verify_generated_bank.py's name-anchoring guard derives its allowed-namespace set structurally from the ontology's own declared owl:Class/ObjectProperty/DatatypeProperty subjects, not a hardcoded 'prodi:' string -- correctly separates CK25's pv: vocab namespace from its prodi: instance namespace even though both prefixes are declared in the same TBox header
- [Phase 07.5-01]: verify_generated_bank.py's top-N strict-extremum check now reads an optional per-example probe field on the bank YAML (generalizing the spike's hardcoded TOPN_PROBES dict); the pre-existing spike bank has no such field yet so its 3 top-N examples pass without probe verification under the promoted gate
- [Phase 07.5-02]: Removed subject-side domain-type constraint from every ShapeTemplate closure (Rule 1 fix) -- CK25's pv:Product/pv:Agent are TBox-declared domains with zero direct instances, silently zeroing value_object/two_hop until fixed; took CK25 bank from 30 to 77 examples, all 9 shapes present
- [Phase 07.5-02]: Used rdfs:label (not CK25's pv:name) as the sole name-anchor predicate in every closure -- empirically verified rdfs:label covers a strict superset of pv:name-carrying subjects, keeping the generator genuinely schema-agnostic
- [Phase 07.5-02]: Force-added reports/generation_report_ck25.json past the reports/ gitignore rule -- that rule targets per-run LLM eval reports; this is a deterministic offline-generator artifact in baseline.json's tier
- [Phase 07.5-03]: slot_preserving checks ONLY binding's filler_label/threshold values (the plan's explicit scope) -- predicate labels/domain names are covered structurally by the intent_lexicon check instead, never re-derived from binding
- [Phase 07.5-03]: Ranking-shape (top_n/offset) direction-flip guard uses a broader antonym set (least/lowest/smallest/cheapest/fewest/minimum/bottom/worst) than either shape's intent_lexicon -- a fixed canonical-direction check since this generator always renders descending/highest order, not a per-example fact
- [Phase 07.5-03]: CK25 bank re-emitted via a test-local _EchoParaphraseClient (deterministic verbatim-echo-with-prefix double) rather than a fixed-list ScriptedLLMClient -- question-aware, scales to all 77 examples, fully offline/no-key; committed paraphrases are SCRIPTED/PLACEHOLDER (flagged in file header + test docstring), superseded by Plan 05's real regeneration
- [Phase 07.5-04]: QALD's dbpedia_subset.ttl has 0 rdfs:domain/rdfs:range declarations AND 0 instance-level rdfs:label triples -- combined with generate_bank_with_report's universal instance-data-bound design (Plan 02), ALL 9 catalog shapes self-drop on TBox-only QALD, not just the 3 data-driven ones (negation/top_n/offset) RESEARCH anticipated -- honest, stronger-than-anticipated finding, not a bug (D-04/D-02 forbid both possible fixes)
- [Phase 07.5-04]: generate_bank_with_report called completely unmodified on QALD (byte-identical to CK25 call); no code change needed -- the committed report JSON's dropped field key already satisfies the plan's grep -q drop check, giving REQ-5's no-ontology-branch claim in its strongest form
- [Phase 07.5-04]: test_generator_no_ontology_branch uses a tokenize-based comment-stripped static scan (not naive str.split) so IRIs containing # are never corrupted and historical Rule-1-fix docstring prose (pv:Product/pv:Agent/weight_g) is correctly excluded as legitimate, non-forbidden documentation
- [Phase 07.5-05]: entity-overlap axis pinned to the real, discovered single-item collision ({'Marketing'}) rather than force-asserted empty — D-05's mitigation design is report+exclude, not zero-tolerance-by-construction; mutating the already regression-tested Plan 02/03 bank would have desynced test_committed_ck25_bank_matches_fresh_regeneration's fixed-seed reproducibility guarantee
- [Phase 07.5-05]: chose the additive few_shot.bank: runner.py config key (RESEARCH OQ-3) over monkeypatch isolation for the generated-bank arms — a committed scripted-ck25-generated-fewshot plumbing arm must be reachable via the standard test_eval.py path -- verified byte-identical for every existing few_shot arm (705 passed/1 skipped)
- [Phase 07.5-05 DEVIATION FIX, mid-plan, discovered during the human's Task-3 credentialed sweep]: two live regen runs (temp 0.1 then 0.9) found paraphrase()/slot_preserving() were only ever offline-validated against a scripted echo-double that masked real-LLM behavior, yielding <3 faithful paraphrases for 43/77 CK25 examples across three mechanisms. Fixed (TDD, offline-only, no live LLM call): (A) paraphrase() now forces novelty via a growing "already-produced" prompt note + raises the attempt budget k*3->k*5 + bumps the DEFAULT client temperature 0.1->0.7; (B) broadened grouped_aggregation ("over"/"greater than"/"exceeding"/"at minimum") and negation ("lack"/"lacks"/"do not have"/"have no"/"not have") intent lexicons; (C) slot_preserving's filler check now normalizes a decimal comma<->period and whitespace runs (never stripping digits/currency codes -- a value- or currency-changing paraphrase is still rejected); (D) _is_degenerate_value_label excludes lookup/value_object candidates whose subject's own rdfs:label is a bare monetary/numeric value (e.g. "0,38 EUR") -- 4 such degenerate CK25 examples dropped, 73/77 remain, zero unrelated drift (filtering happens AFTER the per-predicate shuffle so every other predicate's sampling stays byte-identical). test_committed_ck25_bank_matches_fresh_regeneration/test_committed_ck25_report_matches_fresh_regeneration updated from byte-exact equality to structural (question/query/shape subset + kept/dropped-delta) checks, since the committed bank still carries the OLD generator's scripted output pending the human's real regeneration. Committed vendored/ck25/generated_fewshot_bank.yml was NOT touched. See .planning/phases/07.5-nl-sparql-query-first-synthetic-few-shot-bank/07.5-05-DEVIATION-FIX-SUMMARY.md.
- [Phase 07.5-05 DEVIATION FIX #2, mid-plan, discovered during the human's credentialed faithfulness judge + manual domain/range adjudication]: the two_hop shape's query chains TWO predicates (a near hop off the name-anchored entity, then a FAR hop whose value IS `?result`), but `question_template` named only the near predicate ("Which {far_type} is linked to {entity} via {near_predicate}?") -- a reader could not tell the answer came from the far predicate. Fixed (TDD, offline-only, no live LLM call, query text unchanged): rewrote the template to "What is the {far_predicate} of the {member_type} whose {near_predicate} is {entity}?" and added a new `member_type=pred.domain` slot (the intermediate node's shared domain class) to `_candidates_two_hop`. `test_committed_ck25_bank_matches_fresh_regeneration`'s structural subset check narrowed from `(question, query, shape)` to `(query, shape)` since the committed (pre-fix) bank's two_hop question text now legitimately differs; query-text equality is still checked byte-for-byte. Committed `vendored/ck25/generated_fewshot_bank.yml` was NOT touched (the human's uncommitted real-paraphrase regeneration on disk is untouched). See .planning/phases/07.5-nl-sparql-query-first-synthetic-few-shot-bank/07.5-05-DEVIATION-FIX-2-SUMMARY.md.
- [Phase 07.5-05]: NL-GEN-01 CLOSED via ADOPT path: credentialed 3-run CK25 sweep (gpt-4o-mini, corpus_sha 814d227) shows generated-fewshot beats a fresh zero arm on all 3 runs (paired McNemar p<0.05 raw and overlap-excluded); zero-regression bar met via the SPEC's documented 'b>c on every run' alternative clause (c==0 only on run 3); QALD non-regression trivially met (generated QALD bank is empty). REQ-3 faithfulness recorded as DOCUMENTED-PARTIAL (gpt-4o-mini judge unreliable, manual adjudication ~88-96%) -- non-blocking since paraphrases are unused by FewShotIndex retrieval.
- [Phase 07.5-06]: Stage-2 engine promotion SHIPPED (conditional on Plan 05 ADOPT, user-confirmed). OQ-2 boundary = promote-template-core-only: the pure ontology-agnostic query-shape template catalog (ShapeTemplate + SHAPE_CATALOG + 9 applies/build_sparql closures + render/index helpers) promoted VERBATIM to a new arango_query_core.nl.synthbank engine seam (stdlib-only, no pyoxigraph), pushed to BOTH remotes (engine commit 3438305), ls-remote-verified on both BEFORE uv lock (07.3-02 precedent). bank_generator.py refactored into a thin eval-side shim (-530 lines) keeping data-binding + execution-filter + paraphrase test-side. Pin bumped b669320->3438305 (both [nl]+[dense]). Behavior-identity proven mechanically by the committed CK25+QALD fresh-regeneration-equivalence tests (not asserted). Non-regression: W3C DAWG >=96.4% green, no pyoxigraph on engine import path, transpiler package unchanged. Consumer verified against a local-editable engine BEFORE the push (arango-cypher-py package-extraction pattern). Cypher inherits ShapeTemplate + applies gates (build_sparql is the SPARQL-specific half).

### Pending Todos

- Minor cleanup: legacy `arango_sparql/nl2sparql/_core.py::nl_to_sparql` is a stub returning a comment; real path is `NlPipeline`.

### Blockers/Concerns

- [Phase 06.2-04] AWAITING HUMAN CHECKPOINT (Task 2, checkpoint:human-action): the credentialed live `openai-gpt4o-mini` sweep needs a real `NL2SPARQL_API_KEY` the agent must never hold. Human runs `RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "from tests.nl2sparql.eval.runner import run, write_report; r=run('openai-gpt4o-mini'); write_report(r); print('pass_rate', r.pass_rate); [print(c.name, c.passed) for c in r.cases]"` + `git log -1 --format=%h -- tests/nl2sparql/eval/corpus.yml`, confirms headroom (pass_rate < 1.0), and pastes back aggregate + per-case verdicts + corpus_sha. Then the continuation folds them into baseline.json (Task 3 fold-in) and writes 06.2-04-SUMMARY.md.
- [Phase 5] WP-UI-CAT / WP-UI-TENANT / WP-UI-CORR are backend-blocked (need async introspect, tenant catalogue, translator source-map).
- [Gate] W3C DAWG query-eval coverage must stay ≥ 96.4% throughout the NL workstream (Phases 6–7).
- [Dep] Upstream hard dependency `arangodb-schema-analyzer` pinned ≥0.6.1,<0.7.0.
- [RESOLVED, 07.4-06 re-fold] The fresh credentialed live CK25 sweep on the fixed dump mode (standalone + additive, both re-paired against a same-session fresh entity-alone arm) has been run by the human and folded into baseline.json/REQUIREMENTS.md. NL-ACC-02 is closed as a VALID documented-null; no further re-run is anticipated for this phase.
- [Phase 04-07] AWAITING HUMAN CHECKPOINT (Task 2, checkpoint:human-verify, gate=blocking): Task 1 (7 report-only perf test files) committed (901ed75). Human must: (1) docker compose up -d arangodb (host 8532, DB sparql-to-aql), (2) RUN_INTEGRATION=1 pytest tests/perf -m perf -k "not translate_latency and not execute_overhead and not nl_latency" -q to populate the 6 Docker-gated rows in tests/perf/LATENCY_REPORT.md, (3) optionally RUN_INTEGRATION=1 NL2SPARQL_API_KEY=... pytest tests/perf/test_nl_latency.py -m perf -q for the live-LLM row (never paste the key into any file), (4) confirm LATENCY_REPORT.md is populated and secret-free, (5) reply approved or describe issues. Continuation folds in the final SUMMARY once approved.
- [Phase 04-08] AWAITING HUMAN CHECKPOINT (Task 2, checkpoint:human-verify, gate=blocking): Task 1 (5 docs/howto recipes) committed (f149998). Human must: (1) docker compose up -d arangodb + uv run python main.py so /sparql is reachable, (2) run SELECT+ASK+Service-Description via rsparql --service / Protege SPARQL panel per docs/howto/protege.md and paste the real output into protege.md's transcript block, (3) point a YASGUI instance at /sparql per docs/howto/yasgui.md, run the same SELECT+ASK+Service Description, paste real output into yasgui.md's transcript block, (4) confirm both transcripts are secret-free, (5) reply approved or describe issues. Continuation completes the plan, writes 04-08-SUMMARY.md, and runs the final metadata commit once approved.
- [Phase 07.5-05] AWAITING HUMAN CHECKPOINT (Task 3, checkpoint:human-verify, gate=blocking-human): Tasks 1-2 (overlap audit c677193, additive config arms + run_generated_sweep.py 3a5bcc2, README runbook fbe2069) committed. A mid-plan DEVIATION FIX (paraphrase harness -- see the 07.5-05 DEVIATION FIX decision entry above and 07.5-05-DEVIATION-FIX-SUMMARY.md) has since landed, fixing the root cause that made step 0's live regeneration fall short of REQ-3 (<3 paraphrases for 43/77 examples). A second mid-plan DEVIATION FIX (07.5-05 DEVIATION FIX #2 -- see the decision entry above and 07.5-05-DEVIATION-FIX-2-SUMMARY.md) has since landed too, fixing the ONE real bank-faithfulness defect the credentialed judge + manual domain/range adjudication found: two_hop's NL question now names both the near AND far predicate. Human must (0) regenerate CK25 bank paraphrases for real via the live OpenAICompatibleClient (README.md Section 11.0, BLOCKER) -- now expected to reach K>=3 for all non-degenerate examples with the fixed harness AND a faithful two_hop wording, (1) re-run verify_generated_bank.py, (2) test_committed_ck25_bank_matches_fresh_regeneration/test_committed_ck25_report_matches_fresh_regeneration are ALREADY updated to structural checks (no further test edit needed), (3) run RUN_EVAL=1 NL2SPARQL_API_KEY=... uv run python tests/nl2sparql/eval/run_generated_sweep.py --sweep x3 + the QALD non-regression arm + the >=20-pair faithfulness judge, (4) paste back aggregate + per-case verdicts + McNemar/bootstrap (raw and overlap-excluded) + coverage% + faithfulness% + corpus_sha. Continuation folds results into baseline.json (new sibling key), records the adopt/kill decision, updates REQUIREMENTS.md NL-GEN-01, and completes the plan.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Federation | SPARQL `SERVICE` / federated query | v2 | bootstrap |
| OPTIONAL | DEC-0002 Options B/C (doc-emulation + multi-model) | v2 (travels with federation) | bootstrap |
| Write path | SPARQL 1.1 Update | Out of scope (405) | bootstrap |

## Session Continuity

Last session: 2026-08-05T21:58:07.317Z
Stopped at: Completed 07.5-06-PLAN.md — Stage-2 engine promotion shipped (synthbank seam pushed to both remotes, pin bumped 3438305, bank_generator shim). Phase 07.5 COMPLETE (6/6). Reconciled local main with origin/main via merge (3abb116) before executing.
Resume file: None

## Pending (non-blocking) human action

- **Confirmatory CK25 re-sweep on the FINAL committed bank + promoted engine** (NL-GEN-01 already ADOPTED via the 07.5-05 3-run sweep; this only closes the "measured numbers predate the final artifact / engine promotion" gap). Staged and dry-run-verified (commit 3468f34): `tests/nl2sparql/eval/run_generated_sweep.py --dry-run` green against the promoted engine + 73-example bank. Human runs (key never held by agent): `RUN_EVAL=1 NL2SPARQL_API_KEY=... uv run python tests/nl2sparql/eval/run_generated_sweep.py --sweep` (gpt-4o-mini, temp 0.1, corpus_sha 814d227; run 1x for a quick confirm or 3x for parity with the original protocol). Paste back per-run: zero_pass/generated_pass, McNemar b/c/p (raw + overlap-excluded), bootstrap delta+CI, gains/regressions, QALD non-regression. A continuation folds the result into baseline.json (update phase07_5_generated_fewshot_sweep with a `confirmatory_resweep_2026-08` entry) — expected to reproduce ~13-14/49 generated vs ~5-6/49 zero, b>c, p<0.05.
