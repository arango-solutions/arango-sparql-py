# Design spec: query-first synthetic few-shot bank (per-ontology NL→SPARQL adaptation)

> **Status:** DESIGN — hardened via `/grill-me`, 2026-07-30. Not scheduled. Ready to feed
> `gsd-discuss-phase` / `gsd-plan-phase` as a new phase when prioritized.
> **Related:** [[expasy-schema-context-levers]], [[execution-feedback-self-repair-lever]].

## Problem & goal

Domain matters enormously for NL→SPARQL (a fixed recipe swung 60%→13% between a readable and an
opaque schema; the model floors at 0.2% on DBpedia/QALD). The one lever we have *proven* is few-shot
retrieval (+19pt, BM25). But few-shot needs a per-domain example pool, and hand-curating one for every
new ontology doesn't scale.

**Goal:** at **build time** for any new ontology, auto-generate a `(question, gold-SPARQL)` few-shot
bank so the pipeline is seeded for that ontology. This is **build-time specialization**, not zero-shot
generalization — "auto-onboard each ontology with its own examples," not "hope the model generalizes."

## Non-goals

- **Not an eval or a validity certificate.** The bank is a *prompting aid*. Any generalization claim
  is measured on **held-out human benchmarks**, never on self-generated questions.
- **Not question-first generation.** Having an LLM invent a question and then write its own "gold"
  SPARQL is the oracle problem Phase 07.1 retired (the unreliable component certifies its own labels).
  This design is query-first.

## Design (resolved via grill)

### Q1 — Generation method: template backbone + gated LLM add-on
- **(b) Template backbone (primary).** A small, hand-written, **ontology-agnostic** set of compositional
  SPARQL templates — lookup, value-object fetch, category filter, `COUNT`, top-N (`ORDER BY … LIMIT`),
  `OFFSET`, existence/negation (`FILTER NOT EXISTS`), 2-hop join — whose predicate/class slots are filled
  from the TBox (reuse 07.4's `build_predicate_index` shape classification: value_object /
  category_instance / linked_entity / literal). Valid **and shape-covering by construction**; the
  correctness oracle is the template author, verified once and amortized across all instantiations. This
  is what reaches the *compositional* shapes (aggregation/ranking/negation/multi-hop) where NL→SPARQL
  actually fails — the TBox alone only yields easy single-predicate patterns.
- **(a′) Validated LLM add-on (optional, gated).** LLM proposes SPARQL, then it is filtered through
  parse + transpile + **execute-non-empty**; keep only survivors. Recovers phrasing/shape *diversity*
  beyond the templates without trusting the LLM's SPARQL. Added **only if** coverage measurement shows
  the templates are too narrow. Raw LLM SPARQL (no filter) is rejected.

### Q2 — Faithfulness: paired templates, LLM paraphrases only
- **Paired query/question templates.** Each query template ships with a matching question template
  ("what are the top {N} {C} by {P}?"), so faithfulness is **by construction** — both sides share the
  template.
- **LLM paraphrases for naturalness.** From each templated question, generate **K natural variants**
  ("which products are most expensive?", "show me our priciest items") all mapping to the *same* fixed
  correct query — this defeats the "templated questions are stiff" external-validity risk while keeping
  the query faithful. **Sample-audit** the paraphrases (LLM-judge or round-trip on a subset), not every
  one.
- **(a′) pairs** have no template anchor → a **mandatory LLM-judge faithfulness filter** (accept its
  error rate; another reason a′ is the risky add-on).

### Q3 — Data-binding: generate against live data, filter empties
- **TBox for query shape; live instance data for slot values.** Fill entity/value slots by sampling
  real values from the data (a category IRI with ≥1 member; a country literal that appears); **execute**
  each candidate and keep only non-empty (rows / true / meaningful count). Reuses the execution oracle
  from (a′) as a generation filter — the "planted scenarios guarantee non-empty" discipline, mechanized.
- **Assumption:** representative instance data exists at build time. If a new ontology onboards with
  schema but little/no data, the generator degrades — documented fallback is TBox-only (ungrounded,
  lower quality). The bank couples to a data snapshot, but since examples teach *patterns* not specific
  answers, a stale entity IRI is low-harm.

### Q4 — Retrieval integration: reuse existing machinery
- Reuse `FewShotIndex.from_corpus_files` + **BM25** (proven +19pt; dense parked for cost). The generated
  bank is **another `fewshot_bank.yml`-format file** — drop-in.
- **Per-ontology = per-bank-file:** emit `<ontology>_fewshot_bank.yml`; the config points the arm at it.
- **k** reuses existing sweep values (20–40) — a tunable, not a design decision.
- Extend the existing `test_fewshot_bank_disjoint.py` to **shape-level** as the seed for the overlap
  audit (Q6).

### Q5 — Coverage & bank size (DEFAULT — confirm on review)
- Cover every predicate × its applicable template shapes; **K paraphrases per query** (default 3–5);
  target a few hundred examples, balancing retrieval quality against build cost. Grow the template set
  over time. **Coverage metric:** fraction of held-out failing cases whose *gold query shape* is present
  in the bank.

### Q6 — Measurement: mechanistic + directional (option A)
The benchmark reality forbids a clean powered test: **CK25 (49)** is where the bank's value shows but is
underpowered (~16pt MDE); **QALD (514)** is powered (~6–8pt MDE) but its floor is caused by DBpedia
**entity/IRI grounding**, a bottleneck *orthogonal* to what a shape/predicate bank fixes — so QALD may
show ~0 even for an excellent bank. We therefore adopt on mechanistic + directional evidence, not
significance:
- **Blind generator** (built only from ontology + data, never from held-out questions); **run once**.
- **Cross-ontology:** the *same generator* produces a CK25 bank and a QALD bank; measure both held-out.
  This is the generalization test — the same generator helping *both* domains.
- **Metrics:**
  1. **Shape-coverage** of held-out failures (mechanistic proxy).
  2. **CK25 directional lift**, zero regressions.
  3. **QALD** reported for non-regression + any lift (expected muted — orthogonal bottleneck).
  4. **Overlap audit:** bank↔test query-shape overlap; read all lifts as an **upper bound** until overlap
     is confirmed low, and report the lift **after excluding near-duplicate shapes**.
- **Adopt if:** the same generator lifts CK25 directionally + covers held-out shapes + the lift survives
  overlap-exclusion + zero regressions. **Kill if:** lift collapses after overlap-exclusion, or only one
  ontology benefits.

### Q7 — Build mechanics, cost, staleness (DEFAULT — confirm on review)
- Runs at **ontology-onboard / build time** (offline) — **zero query-time latency**, and no query-time
  DB or LLM dependency (unlike the self-repair loop).
- Per-ontology cost = template instantiation (cheap) + K paraphrase LLM calls per query (bounded) +
  execution filtering. **Cache** the bank; **regenerate** on material ontology/data change.

## Honest caveats / risks

- **Template coverage ceiling** — real users combine shapes the templates miss; measure the miss rate,
  don't assume full coverage.
- **QALD's orthogonal bottleneck** means the only powered set under-reports this lever's value.
- **Build-time data-availability** assumption (with a TBox-only fallback).
- **External validity** is bounded by how representative CK25/QALD are of real user questions — a
  property of the benchmarks, not this design.
- **"Generalizes to ANY ontology"** needs ≥2 independent domains to even start (CK25 + QALD); more later.

## Relationship to Phase 07.1

07.1 retired *question-first synthetic corpus generation for eval* (oracle + external-validity +
SPARQL-fluency risks). This is *query-first generation for a few-shot pool* — a different use that
dodges those reasons (correctness by construction; measured on held-out human sets, not self-graded).
Not re-litigating 07.1's eval decision.

## Next step

Feed `gsd-discuss-phase` / `gsd-plan-phase` as a new phase when prioritized. Corpus growth (07.1) is
**done**; this does not wait on it.
