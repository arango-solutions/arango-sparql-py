# Phase proposal — Relationship-path grounding (NL→SPARQL "seam-8")

**Status:** proposed / scoping · **Date:** 2026-08-06 · **Origin:** root-cause of the CK25 composed-lever evaluation (2026-08)

## 1. Root cause (verified, not inferred)

The composed ceiling on CK25 is `g+f` (entity grounding + query-first few-shot bank) = **16/49 (32.7%)**. The 31 failures were captured with their candidate SPARQL (`dump_candidates.py`) and every candidate executed — **0 malformed, 0 engine-rejected. The problem is 100% semantic.** Verified breakdown:

- **16 EMPTY-result** (dominant): the model **grounds the named entity correctly** but **navigates the wrong predicate-path**, so a valid query executes to nothing.
- 10 wrong-value (counts/rounding/wrong-entity-pick), 3 ASK-kind-mismatch, 2 harness artifacts.

Canonical example — ck25-7, "manager of the Data Services department":

```
CANDIDATE:  <dept-41622> pv:responsibleFor ?x .  ?x pv:hasManager ?result      → 0 rows
GOLD:       ?person pv:memberOf <dept-41622> .   ?person pv:hasManager ?result  → 1 row
```

Entity grounding landed `dept-41622` (a Department). The model then invented a forward path (`Department→responsibleFor→…`) instead of the real **inverse** path (`Person→memberOf→Department`). This is **relationship-path selection**, one level above entity grounding — and it is NOT what full predicate grounding (07.4) addressed, which *dumped* predicates and net-regressed via distraction (`all` arm 12/49 < `g+f` 16/49).

**The 16 missed paths** (their gold predicate chains): 4 one-hop, 7 two-hop, 5 multi-hop (up to 4 hops, e.g. `BillOfMaterial→hasBomPart→hasPart→hasSupplier→country`). Recurring shapes: **inverse edges** (`memberOf`, `responsibleFor`), **manager relations** (`hasManager`/`hasProductManager`), and **supply-chain chains** (`hasBomPart`/`hasPart`/`hasSupplier`).

## 2. Hypothesis

Surfacing the **specific relationship path(s) that connect the question's grounded anchor class to its target** — and *only* those, not the whole schema — converts empty-result failures into correct navigations **without** the distraction that sank full predicate grounding. Mechanical (TBox-only), so it transfers to CDF like seams 6/7.

## 3. Core mechanism — class-connectivity shortest-path retrieval

Not "selective predicate list." The sharper design, dictated by the data:

1. **Anchor class** — from entity grounding (seam 6): the grounded entity's `rdf:type` (e.g. `dept-41622` → `Department`).
2. **Target** — from question-token match against the TBox vocabulary (reuse seam-7's scorer): "manager" → `Manager`/`hasManager`; "email" → `email` datatype prop.
3. **Path retrieval** — over a precomputed **class-connectivity graph** (classes as nodes, predicates as *directed AND inverse* edges from `rdfs:domain`/`rdfs:range`), return the **shortest predicate path(s)** connecting anchor → target (bounded depth, bounded count).
4. **Render** — a compact, imperative navigation hint composed *after* the entity block: *"To relate a Department to its manager: `?p pv:memberOf <Department> . ?p pv:hasManager ?m`."*

Because it surfaces **one path between two already-anchored classes**, not a class's whole neighborhood, the surface stays tiny — this is the specific answer to the 07.4 distraction failure.

## 4. What it builds

- **Engine seam-8** in `arango_query_core.nl` (mirrors seam-6/7 style; pyoxigraph-free; Cypher inherits): a `ClassPathIndex` built from the TBox — directed+inverse class-connectivity graph + bounded shortest-path enumeration + a `format_prompt_section` renderer. Caller-owned construction, no memoization at the layer (seam-6/7 precedent).
- **Adapter wiring**: `path_index()` / `path_prompt_section()` on `QueryLanguageAdapter`, composed after the entity block in `NLQueryEngine._system_prompt`.
- **Eval-side**: a `path_grounding:` config block (mirrors `grounding:`/`predicate_grounding:`), a composed arm `openai-gpt4o-mini-ck25-grounded-generated-fewshot-path`, and its scripted plumbing twin.
- **Reuse**: seam-6 grounded entities (anchor classes), seam-7 `PredicateIndex` (domain/range/shape substrate + token scorer for target detection).

## 5. Key design decisions (open questions)

| # | Decision | Leaning |
|---|---|---|
| D-1 | Path depth cap | ≤3 hops (covers 15/16; the 4-hop supply-chain cases are a stretch goal) |
| D-2 | **Inverse edges** | **Required** — ck25-7/50 fail precisely for lack of them |
| D-3 | Anchor source | grounded-entity `rdf:type` (composes with seam-6, which we know works) |
| D-4 | Target detection | seam-7 token scorer over TBox classes+predicates; multiple targets → multiple paths |
| D-5 | Surface budget | ≤ ~5 paths (THE anti-distraction knob; tight by design) |
| D-6 | Ranking | shortest first; tie-break by question-token overlap on path predicates |
| D-7 | Rendering wording | imperative path template; provisional (07.4 lesson: test, don't freeze) |
| D-8 | No-anchor fallback | if seam-6 grounds nothing, emit nothing (honest no-op) |

## 6. Measurement plan

**Step 0 — offline viability gate (no key, do FIRST; kill/proceed before any spend).** For the 16 empty-result golds, extract each gold's true predicate path; build the class-connectivity graph from the CK25 TBox; check whether bounded shortest-path (depth ≤3, with inverse edges) between the gold's anchor and target classes **recovers the gold path** within the ≤5 budget. This is a mechanical recall gate (cf. the 07.3-04 entity-recall gate). If path-recall is low, the lever can't work — stop here.

**Step 1 — credentialed paired sweep** (human-run, same session, `run_composed_sweep.py` + the new arm): `grounded+few-shot+path` vs the current `g+f` ceiling. Directional + zero-regression (CK25 underpowered, n=49 — same discipline as 07.3–07.5). Watch the distraction guard: `c` (regressions) must stay ~0.

**Success:** converts a meaningful share of the 16 empty-result cases (b>0, c≈0) surviving overlap-audit; no W3C/transpiler regression.

## 7. Risks / kill criteria

- **Distraction re-emerges** (the 07.4 failure) → mitigated by class-anchoring + tight ≤5 budget; measured by the zero-regression guard.
- **Path-recall too low offline** (Step 0) → kill before key spend.
- **Depth explosion** at ≥4 hops → cap at 3; log the dropped 4-hop cases honestly.
- **Transfer** → TBox-walk only, no CK25 hand-curation (D-02 discipline), so it transfers to CDF/Cypher.

## 8. Why this over the alternatives

- **vs catalog expansion (synthbank v2):** that targets the *beyond-catalog* complexity (multi-column/AVG/top-K, ~10 wrong-value cases); this targets the *larger, verified* dominant bucket (16 empty-result path errors). Do this first.
- **vs fine-tuning:** FT could bake these paths in but is **schema-specific** (breaks CDF transfer). Path grounding is mechanical + transfer-preserving; FT is the fallback only if in-context path-teaching plateaus.
- **vs judge fixes:** verified to recover only ~5 pts (ASK-relaxation + IRI/number normalization) — worth doing opportunistically, not the main lever.

## 9. First action

Run **Step 0** (offline path-recall spike) — no key, ~an afternoon — to confirm the class graph actually contains the 16 gold paths before committing to a phase. Then formalize as a ROADMAP phase and plan it.
