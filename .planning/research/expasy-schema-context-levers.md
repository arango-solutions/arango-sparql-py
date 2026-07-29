# Research: Schema-context levers from the ExPASy/SIB federated-SPARQL system

> **Source:** *LLM-based SPARQL Query Generation from Natural Language over
> Federated Knowledge Graphs* (Emonet, Sima, de Farias et al.), arXiv:2410.06062v1.
> Clipped to the vault 2026-07-28. Production system: [chat.expasy.org](https://chat.expasy.org/).
> **Read against:** our own lever inventory in
> [`nl-to-sparql-beyond-prompting.md`](nl-to-sparql-beyond-prompting.md) and
> [`docs/nl2sparql-quality-overview.md`](../../docs/nl2sparql-quality-overview.md),
> plus the confirmed CK25 results (entity-grounding lever, dead EGS lever).
> **Question this note answers:** are there levers in this paper we haven't pulled?

---

> ## ⚠ UPDATE 2026-07-28 — reconcile with completed Phase 07.4 (read this first)
>
> This note was captured without Phase **07.4 (`nl-sparql-predicate-schema-convention-grounding`)**
> in view. 07.4 is **complete and verified** (`status: passed`, 8/8 must-haves,
> `07.4-VERIFICATION.md`). It materially changes the verdicts below:
>
> - **Lever #1 (class-shape / schema-shape context) is NOT un-pulled — it was pulled in 07.4
>   and returned a rigorous NULL on CK25.** 07.4 walks the OWL/RDFS TBox, derives a
>   value_object / category_instance / linked_entity / literal shape per predicate (verified
>   correct against CK25's real TBox: `price`→value_object, `hasCategory`→category_instance,
>   `hasManager` correctly guarded), and injects them as a structural context channel. Result,
>   on a valid unconfounded re-run: **entity-alone 12/49 → entity+predicate 10/49, McNemar
>   p=0.6875** (standalone predicate 7/49, p=0.125). The confounded p=0.0156 from 07.4-05 was
>   SUPERSEDED. So the model was handed the correct legal predicates/shapes and accuracy did not
>   move. The only genuinely untried slice of lever 1 is the paper's *embedding-similarity
>   ranking* of shapes (07.4 injects TBox-scoped, not question-similarity-ranked) — but the null
>   on the injection itself makes it unlikely the ranking refinement alone cracks these cases.
>
> - **Lever #2 (schema-conformance validate-and-repair) is still genuinely un-pulled, and the
>   per-case transcripts (07.4 additive-arm report, gold-anchored) REHABILITATE it as a narrow,
>   evidence-backed bet — correcting an earlier draft of this block that called it mis-aimed.**
>   The 35 CK25 cases that fail in BOTH the entity-alone and entity+predicate arms break down as:
>   **A. empty generation 4 (11%)**; **B. INVENTED predicate 10 (29%)** (`pv:supplier`→`hasSupplier`,
>   `pv:part`→`hasPart`, `pv:hasReliabilityIndex`→`reliabilityIndex`); **C. WRONG *legal* predicate
>   chosen 16 (46%)** (`country` vs `addressCountry`, `hasProductManager`/`responsibleFor` vs
>   `hasManager`); **D. pure structural 5 (14%)** (predicates match gold, wrong join/filter/agg).
>   So the residual is **~74% predicate-related, only ~14% pure structural** — 07.4 aimed at the
>   right target but with the wrong *mechanism* (passive input-side injection).
>   - **Lever 2 (legality repair) cleanly targets bucket B (~10 cases)** — and critically these
>     are cases where 07.4 *injected* `hasSupplier` and the model *still* wrote `pv:supplier`, so a
>     post-hoc "`pv:supplier` is invalid; valid: `hasSupplier`" repair is a stronger signal than
>     anything tried. Realistic clean-fix subset ~5–7 (some bucket-B cases carry multiple invented
>     predicates + co-faults).
>   - **Bucket C (46%, the plurality) is beyond BOTH paper levers**: the predicate is *legal* so
>     lever 2's legality check passes it, and lever 1's injection already failed to steer the
>     choice. This is a predicate-**disambiguation** problem (per-predicate descriptions/examples
>     distinguishing near-synonyms like `country`/`addressCountry`) or an execution-result-feedback
>     problem — the genuinely unsolved lever, and it is NEITHER of the paper's two.
>
> - **Net revision to the "Recommended sequence" below:** lever 2 is worth a *scoped* phase aimed
>   at bucket B (invented predicates), with eyes open that its CK25 ceiling is ~5–7 cases and the
>   plurality failure mode (bucket C) is untouched by it. The higher-value un-pulled idea is
>   predicate-disambiguation / execution-result feedback for bucket C, which the paper does not
>   cover. Corpus growth (step 1 / Phase 07.1) is still the gate: 07.4 is direct evidence a
>   schema-context lever cannot be shown to move the number at this eval size (additive-arm
>   discordant pairs b=2/c=4 — "no evidence of lift," not "proven zero"). Method caveat: the
>   A/B/C/D split is from gold-vs-generated predicate-SET comparison (regex, not full execution
>   diff), on gpt-4o-mini — a stronger generator would likely shrink bucket B and shift weight
>   further onto the unsolved bucket C.
>
> *The original note is preserved unchanged below for provenance; treat its lever verdicts as
> superseded by this block.*

---

## What the paper is

A three-stage RAG pipeline for NL→federated-SPARQL over bioinformatics KGs
(UniProt, Bgee, OMA):

1. **Retrieve context** by embedding-similarity search over two indexed channels:
   (a) example question/query pairs harvested from each endpoint, and
   (b) auto-generated **class shapes** (human-readable ShEx derived from VoID
   descriptions — which predicates a class supports and what classes/datatypes
   they point to).
2. **Build the prompt** from the top-similar questions+queries and the
   top-similar class labels+shapes, alongside the user question.
3. **Validate and correct**: parse the generated SPARQL, extract triple patterns,
   and check each predicate against the subject class's allowed predicates from
   the VoID schema. Emit human-readable errors ("subject `?disease` of type
   `up:Disease` does not support `rdfs:label`; valid predicates: `skos:prefLabel`,
   `rdfs:comment`, …") and feed them back to the LLM to repair.

Eval is small: **13 held-out questions × 3 runs**. RAG w/o validation took gpt-4o
from F1 0.08 → 0.85; adding the validation loop took it 0.85 → **0.91**, and
validation "is particularly valuable for smaller LLMs." Treat all magnitudes as
directional.

## Mapping to our lever inventory

| Paper component | Our status | Verdict |
| --- | --- | --- |
| Few-shot example retrieval (§2.1–2.2) | **Pulled** — BM25 +19pt confirmed; dense parked | Not novel |
| Entity/instance grounding | **Ahead of them** — we inject explicitly retrieved instance IRIs (CK25 12%→24.5%, p=0.031); they ground only implicitly via IRIs inside retrieved example queries | We lead |
| Execution-based result scoring — Success / Different Result / No Result / Error (§4) | **In flight** — Phase 07.2 (`execution-based-eval-judging`) | Adopt their 4-way taxonomy |
| **Class-shape retrieval into the prompt (§2.1–2.2)** | ~~Not pulled~~ → **PULLED in Phase 07.4 → NULL** (see UPDATE) | ~~Un-pulled lever #1~~ Tried, no CK25 lift |
| **Schema-conformance validate-and-repair loop (§2.3)** | **Not pulled** — distinct from the dead EGS | Un-pulled lever #2 — **scoped to bucket B (invented predicates, ~29% of residual, ~5–7 clean-fixable); bucket C wrong-legal-choice (46%) is beyond it. See UPDATE**|
| Endpoint-routing metadata (schema.org per endpoint) | N/A to single-schema eval | CDF-horizon only |

## The two genuinely un-pulled levers

### 1. Schema-shape retrieval into the prompt — *structural context channel*

Generate a compact, human-readable shape per class (ShEx-style: the predicates a
class legally supports and what classes/datatypes each points to), index them, and
retrieve the shapes most similar to the question — injected alongside the few-shot
examples.

- This is **structural** context, distinct from both our few-shot examples and our
  instance-IRI grounding. It tells the model *which predicates are legal for a
  class and what they connect to*, before generation.
- It targets the exact residual failure mode our CK25 diagnosis flagged as the
  *other half* of the bottleneck after entity grounding: **schema conventions**.
- **We already own the raw material.** `arango-schema-mapper` produces OWL/RDFS;
  we can emit ShEx-style shapes from it. No new upstream dependency.
- Engine-side (a new retrieval channel on the existing few-shot seam) → the sister
  Cypher project inherits it.

### 2. Schema-conformance validate-and-repair loop — *not the EGS we killed*

Deterministically check that every triple pattern's predicate is actually allowed
on its subject's class in the schema; if not, hand the model a human-readable
correction and retry.

- **Do not confuse with EGS.** Execution-guided *selection* over samples gave
  ~0 lift on CK25 (systematic, not stochastic, failures). This is a different
  mechanism: a **predicate-legality check** producing a targeted repair signal.
- Our current validator checks only **transpilability**, not **schema
  conformance** — a query can transpile cleanly while using a predicate that
  doesn't exist on that class. This is a genuinely new repair signal.
- In the paper it lifted even gpt-4o (0.85→0.91) and helped weaker models most.
- Engine-side repair-hint seam → Cypher inherits it.

Levers 1 and 2 are the input and output sides of the same bet: **make the schema
legible to the model** (channel it in on retrieval; enforce it on repair).

## CDF-horizon note (not for the current eval)

Their endpoint-routing metadata (schema.org descriptions per endpoint, used to
pick *which* endpoint a triple pattern resolves against) is federation-specific and
irrelevant to our single-schema eval — but it maps directly onto the CDF federated-
query vision. Park it as a CDF-milestone reference, not a v1.1 NL lever.

## Caveats

- **Tiny eval.** 13 questions × 3 runs; F1 magnitudes will not transfer. Same
  schema-dependence caveat we already carry (a fixed recipe swung 60%→13% between a
  readable and an opaque schema).
- **Both levers are schema-context levers**, and our CK25 diagnosis already named
  "schema conventions" as the residual bottleneck after entity grounding — a strong
  prior they're aimed at the right target. But the **measurement ceiling still
  gates proof**: at 25 cases MDE ≈ 16pt. Corpus growth (Phase 07.1) remains the
  prerequisite before either lever can be shown to move the number.

## Recommended sequence

1. **07.1 — synthetic corpus growth** (unchanged prerequisite; removes MDE ceiling).
2. **07.2 — execution-based judge**: adopt the 4-way Success / Different Result /
   No Result / Error taxonomy while building it.
3. **v1.1 — schema-conformance validate-and-repair loop** (lever 2): highest ROI,
   reuses owned infra, targets a confirmed failure mode, engine-side.
4. **v1.1 — class-shape retrieval channel** (lever 1): input side of the same bet.
5. **Then** generator fine-tuning (unchanged; highest ceiling, favorable readable-
   schema domain).
6. **CDF milestone** — revisit endpoint-routing metadata for federation.

## Where we already lead the paper

Explicit instance-IRI entity grounding is a lever we've confirmed and they don't
have. Worth remembering when reading their F1s: their strong numbers come from
example+shape retrieval *without* the entity-grounding channel we've already proven.
