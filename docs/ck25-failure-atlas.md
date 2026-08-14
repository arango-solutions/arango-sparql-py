# CK25 NL→SPARQL Failure Atlas

**Purpose.** Every prior audit re-derived "the model gets the entity/predicate/path
wrong," shipped a schema-grounding lever (07.3 entity, 07.4 predicate, 07.6 path), and
measured ~no lift. This atlas is the evidence-grounded, per-case root-cause map so the
next audit starts here instead of repeating that loop.

**Scope.** The 28 CK25 cases that fail under **every** arm of the composed sweep
(zero / entity-ground / predicate-ground / few-shot / g+f / g+f+path). `g+f` (grounding +
few-shot) is the ceiling at 16/49; these 28 are the residual it cannot reach.

**Method.** Gold SPARQL from `tests/nl2sparql/eval/vendored/ck25/corpus.yml`; generated
SPARQL from `tests/nl2sparql/eval/reports/openai-gpt4o-mini-ck25*.json` (per arm); answer
sets executed through pyoxigraph against `vendored/ck25/raw/prod-inst.ttl`; verdicts from
`composed_sweep_result.json`. Not vibes — every category below is backed by the actual
generated query and its executed answer set.

---

## Headline

The residual is **not** a vocabulary-grounding problem, which is why four grounding-lever
phases moved nothing. It splits two ways:

| Bucket | Cases | Fixable by… |
|---|---:|---|
| **Model-side: analytic query composition** | ~18 | query-**shape** few-shot; NOT more schema IRIs |
| **Eval-side / unwinnable-by-design** | ~10 | fixing the corpus/judge, or accepting a ceiling |

~30% of the "failures" are eval-design contamination (ambiguous questions, internally
inconsistent gold conventions, over-strict judge), not model capability. Grounding cannot
touch **either** bucket: the simple-lookup cases it *could* help already pass.

## Root-cause families (28 never-pass cases)

| Family | Count | What actually happens |
|---|---:|---|
| **COMPOSITION** — nested aggregation, GROUP BY / HAVING, OPTIONAL, subqueries, multi-hop paths | 11 | Model emits a plausible but structurally-wrong query; usually runs to **empty** (over-constrained) or wrong rows |
| **COUNTRY-CONVENTION** — gold set is internally inconsistent | 4 | Country is modeled two ways: `pv:addressCountry "France"` (literal, on Agent) **vs** `pv:country <dbpedia:…>` (entity edge, on Supplier). Gold picks one; model picks the other and/or botches the country value |
| **DROPPED-CATEGORY** | 2 | Under analytic load ("heaviest/densest coil") the model drops the `hasCategory <prod-cat-Coil>` filter and ranks *all* Hardware |
| **SUPERLATIVE** — ORDER BY … LIMIT | 2 | Right idea, wrong scope/projection |
| **NEGATION** — FILTER NOT EXISTS / ASK | 2 | Negation mis-structured → wrong/empty |
| **AMBIGUOUS-NL** | 2 | Question underdetermines the query; gold picked one reading the model can't guess |
| **JUDGE-ARTIFACT** | 2 | Model answer is **correct**; the answer-set judge rejects it on shape |
| **MULTI-HOP / INVERSE-JOIN** | 1 | The 07.6 path target; path mechanically retrievable offline but still wrong live |
| **ASK / NEGATIVE-GOLD** | 2 | Gold answer is "no"/false; model asserts yes |

## Why the three grounding levers can't help (and 07.4 sometimes hurt)

- The cases grounding *could* fix (which IRI / which predicate) **already pass** — they're
  the simple lookups (ck25-1,2,3,5,6,8,…).
- The residual needs query **structure** (COUNT/GROUP BY/HAVING/OPTIONAL/negation/nested
  subqueries) or is eval-contaminated (convention/ambiguity/judge). Injecting more schema
  identifiers changes the *vocabulary* in the generated query, not its *shape*.
- **Predicate grounding actively distracts** (the 07.4 regression, caught in the raw
  output): ck25-13 under `g+pred` degenerates into `FILTER(?supplier IN (…~50 IRIs…))` —
  the model pastes the injected identifiers instead of reasoning.

## Two concrete, fixable model bugs (not benchmark noise)

1. **Dropped category filter under analytic load** (ck25-21, ck25-25). ck25-25's density
   math was actually fine (unit scaling is rank-invariant); it fails *only* because it lost
   the "Coil" scope. A prompt rule or a shape exemplar ("superlative over a category keeps
   the category filter") could recover these.
2. **Judge over-strictness** (ck25-18: correct cheapest oscillator, rejected for a second
   projected column; ck25-43: correct mutual-compat pairs, rejected for returning both
   directions). At n=49 that's ~4 points of pure measurement noise counting correct answers
   as failures. Canonicalize projection / tolerate extra bound columns.

## Per-case table

`gold#` / `gen#` = answer-set row counts (gold vs entity-grounded arm), executed live.

| case | gold# | gen# | family | one-line root cause |
|---|---:|---:|---|---|
| ck25-4  | 1 | 0 (empty) | COMPOSITION | multi-hop join + `CONTAINS(name,"Sabrina")`; over-constrained → empty |
| ck25-7  | 1 | 10 (wrong) | MULTI-HOP/INVERSE | "manager of Data Services" needs `memberOf`←person→`hasManager`; returned wrong people |
| ck25-9  | 1 | 1 (wrong) | COMPOSITION | COUNT with **two** `hasCategory` (Sensor AND Switch) intersected |
| ck25-13 | 1 | 1 (wrong) | COUNTRY-CONVENTION | gold `addressCountry "France"`; model `pv:country dbo:Country` + `CONTAINS(STR(?supplier))` |
| ck25-15 | 1 | 0 (empty) | COUNTRY-CONVENTION + superlative | cheapest Encoder, FR/DE supplier; convention + over-constrained |
| ck25-16 | ASK:false | 1 | ASK/NEGATIVE-GOLD | "suppliers in Toulouse?" — data has none; gold=false, model asserted rows |
| ck25-18 | 1 | 1 | **JUDGE-ARTIFACT** | correct cheapest oscillator; rejected for extra `?price` column |
| ck25-19 | 1 | 1 (wrong) | SUPERLATIVE | most expensive service; wrong scope/price path |
| ck25-20 | 1 | 0 (empty) | SUPERLATIVE + composition | manager of most-expensive service |
| ck25-21 | 1 | 1 (wrong) | **DROPPED-CATEGORY** | heaviest coil ≤15×15; dropped `hasCategory Coil`, ranked all Hardware |
| ck25-25 | 1 | 1 (wrong) | **DROPPED-CATEGORY** | densest coil; density math fine, dropped `hasCategory Coil` |
| ck25-26 | 10 | 0 (empty) | COUNTRY-CONVENTION | US suppliers' cities; used both country conventions → over-constrained |
| ck25-27 | 47 | 0 (empty) | NEGATION + COMPOSITION | non-managers directory; `subClassOf*` + `NOT EXISTS` + OPTIONAL + ORDER |
| ck25-28 | ERR/ASK | 0 | COMPOSITION | nested ASK subquery; BOM parts from Russia |
| ck25-29 | 5 | 4 (partial) | COMPOSITION | "6th–10th most expensive" (gold window may be off-by-one) + property paths |
| ck25-32 | 246 | 246 (near) | COMPOSITION | per-supplier avg price; GROUP BY/ROUND — **close**, rounding/grouping diff |
| ck25-33 | ASK:false | 6 | NEGATION/NEG-GOLD | depts with no manager; gold=false, model returned rows |
| ck25-34 | 250 | 0 (empty) | COMPOSITION | supplier rolodex; 3 OPTIONALs, model over-constrained |
| ck25-35 | 1938 | 0 (empty) | COMPOSITION | compatible-product price diffs; `subClassOf*` + property paths |
| ck25-36 | 3 | 0 (empty) | **AMBIGUOUS-NL** | "top three skills" → gold reads hardware categories by count |
| ck25-37 | ERR | 0 | COMPOSITION | BOM part count + SUM(qty) + HAVING>600 + ORDER |
| ck25-40 | 48 | 0 (empty) | NEGATION | hardware with no product manager; `NOT EXISTS` property path |
| ck25-41 | 6 | 1 | COMPOSITION | % of team in same dept; two nested GROUP BY subqueries + arithmetic (hardest) |
| ck25-42 | ERR | 0 | COMPOSITION | BOM highest avg unit cost; nested GROUP BY + arithmetic |
| ck25-43 | 969 | 1938 | **JUDGE-ARTIFACT** | correct mutual-compat pairs; gold dedupes direction via `STR(?a)<STR(?b)`, model returns both |
| ck25-44 | 93 | 10 (partial) | **AMBIGUOUS-NL** | "top 10%": model did top-10 or ≥90%·max; gold uses min+0.9·range |
| ck25-46 | 5 | 0 (empty) | COMPOSITION | top-5 suppliers by avg reliability; GROUP BY AVG ORDER LIMIT |
| ck25-48 | 3 | 0 (empty) | COUNTRY-CONVENTION + multihop | BOMs with a Polish-supplier part; `pv:country <dbpedia:Poland>` + multi-hop |

## Recommendations (in priority order)

1. **Fix the judge's projection over-strictness first** (cheap; unblocks honest
   measurement). Tolerate extra bound columns / canonicalize projection & pair-direction.
   Recovers ck25-18, ck25-43, and de-noises the metric so a real lever is detectable at
   n=49 — otherwise the next experiment gets misread again.
2. **Stop injecting schema vocabulary.** Entity/predicate/path grounding is saturated;
   predicate grounding actively regresses (IN-list dump). More of the same won't move CK25.
3. **Invest in query-*shape* few-shot** (the 07.5 synthbank direction — the only lever that
   ever adopted). Add exemplars for the missing shapes: nested aggregation, GROUP
   BY/HAVING, OPTIONAL, negation, superlative-over-a-category (which also targets the
   dropped-category bug).
4. **Decontaminate the benchmark, explicitly.** Reconcile the country convention (or accept
   it as dual-valid in the judge), and bucket the genuinely-ambiguous / latent-formula /
   likely-buggy golds (ck25-25 density, ck25-36, ck25-44, ck25-29, ck25-30 `?depty` typo)
   as *unwinnable-by-design* so they stop being counted against model quality.

## Results — what we actually tried (2026-08-14)

Recommendations 1 and 3 were built and measured on a credentialed same-session
CK25 sweep (gpt-4o-mini, n=49). **Both moved the number** — the first levers in
this project's NL→SPARQL work to do so cleanly:

- **Rec 1 — judge answer-content relaxation** (committed `55c00c6`): grade on the
  gold's answer values, tolerating extra descriptive columns and duplicate/symmetric
  rows. Effect: every arm rose a few points as correct-but-mis-scored answers began
  passing (e.g. zero 5→8, ground 12→17, g+f 16→18). Recovered ck25-18/19/43. Strict
  superset — no previously-passing case regresses; scripted gold-vs-gold invariant holds.
- **Rec 3 — analytic-shape few-shot bank** (committed `8aabe8f`): +11 execution-verified
  exemplars (superlative-over-category, grouped-superlative, negation, count-with-filter,
  nested-subquery) into the query-first bank. **`g+f-analytic` = 22/49 (0.449) — the best
  arm in the project**, vs `g+f` 18/49. Contrast `b=5 c=1 p=0.2188 Δ+0.0816 CI[0.000,0.184]`:
  a directional lift (wins ck25-18/19/20/50/12, mostly superlatives), one distraction
  regression (ck25-11, a lookup). Not a clean adopt at n=49 (underpowered, p>0.05, c≠0) but
  the strongest signal to date.

**What the bank fixed vs didn't — the key learning:**
- ✅ Fixed the **plain superlatives** (single ORDER BY … LIMIT): ck25-18/19/20/50.
- ❌ Did NOT fix **superlative-over-a-category** (ck25-21/25 — the dropped-category bug) or
  **negation** (ck25-27/33/40) — even though the correct-shape exemplar *is* retrieved for
  these. So for the hard cases the wall is **conversion, not retrieval**: the model *sees*
  a `top_n_category` / `negation` exemplar and still drops the category filter or mis-builds
  `NOT EXISTS`. A shape-aware retrieval refinement (committed `157d9f1`, opt-in
  `few_shot.shape_aware`) confirmed this — it only changes retrieval for 2 nested cases; the
  enriched bank already surfaces the right shape for the rest, yet they still fail.
- **Implication:** more/better exemplars have diminishing returns on the residual. The
  remaining bucket-1 wall (analytic *composition*: keep-the-filter superlatives, negation,
  nested aggregation) points at the research's #1 ceiling-mover — **fine-tuning the generator
  on synthetic complex-query pairs** (enabled by the 07.5 synthbank generator) — not more
  prompt context. See `.planning/research/nl-to-sparql-beyond-prompting.md`.

Arms wired for re-sweep: `g+f-analytic`, `g+f-analytic-aware` (in `run_composed_sweep.py`).

## Provenance

- Verdicts: `tests/nl2sparql/eval/composed_sweep_result.json` (credentialed sweep,
  gpt-4o-mini, n=49, execution judge, engine pin `1ec6789`).
- Gold: `tests/nl2sparql/eval/vendored/ck25/corpus.yml`; instances:
  `vendored/ck25/raw/prod-inst.ttl`; ontology: `vendored/ck25/ontology.ttl`.
- Generated: `tests/nl2sparql/eval/reports/openai-gpt4o-mini-ck25{,-grounded,-predicate-grounded,-grounded-predicate-grounded}.json`.
