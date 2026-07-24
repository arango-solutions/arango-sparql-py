# NL→SPARQL eval harness — reproducibility runbook

This directory holds the NL→SPARQL evaluation harness. It has two distinct
paths, and keeping them separate is the whole point of this runbook:

- **`scripted`** — the **no-network, key-free CI default**. Deterministic,
  gates `baseline.json`, never touches a provider. This is what CI runs.
- **`openai-gpt4o-mini`** — the **credentials-gated live-model baseline**.
  Run manually / nightly, out of band, with a real key in the environment.
  Its numbers are hand-folded into `baseline.json` after a human review.

The live baseline is the *measurable floor* Phase 7's few-shot lift is
proven against, so it must be reproducible from the documented steps below
(model + temperature + corpus revision), not a one-off number.

Files:

| File | Role |
|------|------|
| `corpus.yml` | Gold NL→SPARQL cases (positives + `expect_refusal` negatives). |
| `configs.yml` | Provider/judge configs (`scripted`, `openai-gpt4o-mini`, plus per-set `scripted-qald9plus`/`scripted-ck25` — §8). |
| `runner.py` | `run()`, `write_report()`, the canonical-algebra judge. |
| `baseline.json` | The **only** checked-in report artifact — the regression gate (separate top-level entry per set, §8.4). |
| `test_eval.py` | The `@pytest.mark.eval` gate (behind `RUN_EVAL=1`). |
| `power.py` | Pure-Python `required_n`/`achieved_mde` (§8.3). |
| `vendored/{qald9plus,ck25}/` | Public-benchmark adoption: converted corpora + CC-BY-4.0 provenance (§8). |
| `reports/` | **Gitignored** `write_report()` output (raw per-case JSON + Markdown). |

---

## 1. Setup

Install the repo plus the `nl` extra (rule 100 — use `uv`, not bare `pip`):

```bash
uv sync --extra nl        # pins arango-query-core (git ref), rdflib, rank_bm25
# or:  pip install -e '.[nl]'
```

---

## 2. The key-free CI default (scripted — no network)

This is what CI runs and what you should run before every commit. It needs
**no API key** and makes **no network call**:

```bash
RUN_EVAL=1 pytest -m eval -q
```

It runs `run("scripted")` against `baseline.json`: the aggregate pass_rate
must not regress, no baseline-passing case may regress, and every new corpus
case must pass before it is added to `baseline.json`. The scripted pass-rate
tests the **judge**, not the model — do not read it as model accuracy.

---

## 3. The credentials-gated LIVE sweep (openai-gpt4o-mini)

> **Pitfall 1 — the runner's live path reads `NL2SPARQL_API_KEY`, NOT
> `OPENAI_API_KEY`.** `runner._client_for` builds `OpenAICompatibleClient`
> with no explicit key, so it falls to `os.getenv("NL2SPARQL_API_KEY", "")`.
> The `OPENAI_API_KEY` fallback only exists in `get_default_client()`, which
> the runner does **not** use. A missing/blank `NL2SPARQL_API_KEY` posts an
> empty bearer and **401s loudly — it does not fall back or silently degrade.**

Export the key **into this shell only** (never commit it, never paste it back
into any file or chat):

```bash
export NL2SPARQL_API_KEY=sk-...          # your OpenAI key — this shell only
export NL2SPARQL_MODEL=gpt-4o-mini       # optional; configs.yml already pins the model
```

Capture the corpus revision you are measuring against (the `corpus_sha` to
pin into the baseline — a pass-rate without a corpus revision is meaningless):

```bash
git log -1 --format=%h -- tests/nl2sparql/eval/corpus.yml
```

Run the live sweep. It writes `reports/openai-gpt4o-mini.{json,md}` (both
**gitignored**) and prints the aggregate + per-case verdicts:

```bash
RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "from tests.nl2sparql.eval.runner import run, write_report; r=run('openai-gpt4o-mini'); write_report(r); print('pass_rate', r.pass_rate); [print(c.name, c.passed) for c in r.cases]"
```

Cost/latency magnitude: gpt-4o-mini at ≈$0.00015/1k input + $0.0006/1k
output, with `max_repairs=2` (up to 3 calls/case) over a ~25-case corpus, a
full sweep is **≈ 1–3 US cents and seconds-scale**. Cost is a non-issue; the
value is the reproducible number.

---

## 4. Headroom check (do this before promoting anything)

The printed `pass_rate` **must be meaningfully < 1.0**. Headroom is only
observable on the **live** config (the scripted rate tests the judge, not the
model — Pitfall 5). If the live run is at/near ceiling, the corpus lacks
headroom: a Phase-7 few-shot lift would be unmeasurable (Critical Failure
Mode 2). **Do not promote a near-ceiling live baseline** — harden the corpus
first, then re-sweep.

---

## 5. The MANUAL, human-reviewed fold-in into `baseline.json`

> **Pitfall 2 — `write_report()`'s schema ≠ `baseline.json`'s schema.**
> `write_report` emits a **flat** shape `{config, pass_rate, cases:[{name,
> passed, elapsed_ms}]}` into gitignored `reports/`. `baseline.json` is the
> **nested** regression gate `{configs: {name: {...}}}`. Promoting live
> numbers is therefore a **manual, human-reviewed** copy — the same
> discipline as goldens. **CI never auto-regenerates `baseline.json`.**

By hand, add a sibling `configs['openai-gpt4o-mini']` entry to
`baseline.json` (do **not** touch the `scripted` entry). Copy only the
aggregate `pass_rate` / `passed` / `total` and the per-case `{name: passed}`
verdicts from the run, and **add** the three reproducibility fields:

```json
{
  "configs": {
    "scripted": { "...": "unchanged" },
    "openai-gpt4o-mini": {
      "pass_rate": 0.xx,
      "passed": NN,
      "total": 25,
      "cases": { "people-with-names": true, "...": false },
      "model": "gpt-4o-mini",
      "temperature": 0.1,
      "corpus_sha": "<the SHA from step 3>"
    }
  }
}
```

- `model: "gpt-4o-mini"` and `temperature: 0.1` — `temperature` is hardcoded
  in `OpenAICompatibleClient` and `configs.yml` cannot override it today.
  gpt-4o-mini is **not** bit-deterministic even at low temperature
  (Pitfall 6), so recording model + temperature + `corpus_sha` is what makes
  the number interpretable on re-run.
- `corpus_sha` — the `git log` short SHA from step 3.

The entry is validated no-network by `BaselineConfig` (see
`test_live_baseline_companion_structural` in `test_eval.py`), which also
asserts `0.0 < pass_rate < 1.0` (headroom).

---

## 6. Discipline callouts (secret & payload hygiene)

- **NEVER commit a key or bearer token** to `corpus.yml`, `configs.yml`,
  `baseline.json`, this README, or anywhere else. Keys live only in the
  `NL2SPARQL_*` environment variables.
- **NEVER commit raw prompts/completions.** They embed the full ontology and
  could embed a mistakenly-pasted key. They stay in gitignored `reports/`.
  Only the aggregate numbers + model/temperature/corpus_sha cross into
  `baseline.json`.
- **`scripted` stays the CI default.** The live provider is reachable *only*
  via the non-`scripted` config, behind `RUN_EVAL=1` + a key, run manually.
  The default test path never hits the network (rule 200).
- **Never auto-regenerate `baseline.json` in CI** — the fold-in is always a
  reviewed human step.

---

## 7. The Phase 7 dense few-shot lift sweep

This section documents the credentialed, human-run measurement behind
NL-FEW-02: does dense few-shot retrieval produce a **statistically
supported** pass-rate lift over a freshly-run zero-shot arm? It follows the
exact discipline of §§3–6 above (key-gated, `scripted` stays the CI default,
manual human-reviewed fold-in) with the additions the dense arm requires.

### 7.1 Install (the only path that pulls torch)

```bash
uv sync --extra dense       # pulls sentence-transformers + torch (arango-query-core[dense])
```

Pre-warm the HF model once so subsequent runs can go fully offline (D-03
reproducibility):

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', revision='7dbbc90392e2f80f3d3c277d6e90027e55de9125')"
export HF_HUB_OFFLINE=1   # after the pre-warm, guarantee no further network calls
```

**Package legitimacy (blocking, before the first install):** confirm
`sentence-transformers` (https://pypi.org/project/sentence-transformers/) and
`torch` (https://pypi.org/project/torch/) are the legitimate, widely-used
packages before running `uv sync --extra dense` — this is the cheap-insurance
check the RESEARCH slopcheck audit calls for even though it returned clean.

### 7.2 Design: 3-arm self-baselining, N >= 5 runs per arm

Each model (`gpt-4o-mini` anchor, `gpt-5-mini`, `gpt-5`) runs its own
zero/dense/bm25 arm set (D-07). Run **each arm N >= 5 times** (raised from an
earlier N=3 draft — B1): a single run is not trustworthy since gpt-4o-mini
is not bit-deterministic even at low temperature.

Live model-resolution check, BEFORE running any part of the sweep (Open
Question 3 / Pitfall 3 — bare `gpt-5`/`gpt-5-mini` aliases can shift which
dated snapshot they resolve to):

```bash
python -c "
import os, requests
r = requests.get('https://api.openai.com/v1/models', headers={'Authorization': f\"Bearer {os.environ['NL2SPARQL_API_KEY']}\"})
r.raise_for_status()
ids = {m['id'] for m in r.json()['data']}
for alias in ('gpt-4o-mini', 'gpt-5-mini', 'gpt-5'):
    print(alias, 'resolves' if alias in ids else 'MISSING — human decision needed')
"
```

A 404/missing alias is a **human decision point** (swap to
`gpt-5.4-mini`/`gpt-5.5`) — never a silent substitution. Record whichever
resolved snapshot id you observe into the provenance you fold into
`baseline.json`.

Per-arm invocation (mirrors §3's one-liner; export `NL2SPARQL_API_KEY` into
this shell only):

```bash
RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "
from tests.nl2sparql.eval.runner import run, write_report, paired_mcnemar, bootstrap_paired_delta
r = run('openai-gpt4o-mini-dense')
write_report(r)
print('pass_rate', r.pass_rate)
[print(c.name, c.passed) for c in r.cases]
"
```

Repeat for every `(model, arm)` combination in `configs.yml`'s Phase 7 block,
N >= 5 times each. **Run each model's zero arm freshly IN THE SAME SESSION as
its dense arm** — the confirmatory comparison (below) is dense-vs-
freshly-run-zero, never dense-vs-the-06.2-committed-number (M2).

### 7.3 PRIMARY confirmatory test (pre-registered, THE pass/fail bar)

On the **gpt-4o-mini anchor only**: compare the dense arm vs a freshly-run
zero arm, **paired over the same 25 cases**, using the pure-Python helpers
added in Task 2:

```python
from tests.nl2sparql.eval.runner import run, paired_mcnemar, bootstrap_paired_delta

zero = run("openai-gpt4o-mini")          # freshly run THIS session, same snapshot
dense = run("openai-gpt4o-mini-dense")

zero_cases = {c.name: c.passed for c in zero.cases}
dense_cases = {c.name: c.passed for c in dense.cases}

b, c, p = paired_mcnemar(zero_cases, dense_cases)
delta, lo, hi = bootstrap_paired_delta(zero_cases, dense_cases)
print(f"b={b} c={c} p={p:.4f}  delta={delta:.3f} CI=({lo:.3f}, {hi:.3f})")
```

**The lift PASSES iff McNemar `p < 0.05`.** This single test — on the
gpt-4o-mini anchor, dense vs freshly-run zero, paired over the same 25 cases
— is THE confirmatory bar for NL-FEW-02 (m1/B1/M2). Report `b`, `c`, the
exact p-value, and the bootstrap paired-delta 95% CI.

### 7.4 SECONDARY checks (noise floor, MDE, continuity — never the pass/fail bar)

- **Per-(model, arm) standard deviation** across the N >= 5 runs is a
  noise-floor sanity check only, NOT a global max-over-arms range and NOT
  the pass/fail bar (B1).
- **Minimum detectable effect (MDE):** at n=25 and a base pass-rate ~0.32,
  the paired McNemar design detects roughly a **4-case (~16pt) lift** at
  `p < 0.05`. A smaller true lift may not reach significance — **do not
  over-read a null result** against this design's actual power.
- **Continuity check against the committed 06.2 baseline (0.32):** dense vs
  0.32 is a SECONDARY signal only, and is **INVALID if the resolved model
  snapshot differs from 06.2's** — record both snapshot ids and flag
  accordingly. The confirmatory comparison is always dense-vs-
  freshly-run-zero in the same session (M2).

### 7.5 EXPLORATORY: capability tiers + dense-vs-bm25 (report unfiltered)

The `gpt-5-mini` / `gpt-5` tiers and the dense-vs-bm25 comparison are
**EXPLORATORY** — report all of them, in full, **never cherry-picked** for
whichever tier happens to show a lift (m1). A null result on the flagship
(`gpt-5` already saturating zero-shot — a ceiling effect) is a **finding**,
not a phase failure. Dense-vs-bm25 is explicitly **uninterpretable as a
null** at the ~18-24-item bank size used here (m3) — do not read a bm25 tie
as "dense doesn't help."

### 7.6 Report BOTH install numbers (M3)

- **DEFAULT-INSTALL number = the bm25 arm.** Production `SparqlAdapter`
  requests `mode="auto"` (D-05); a plain `.[nl]` install (no `.[dense]`
  extra) never runs dense in production — it degrades to BM25 then no-op.
  This is the honest number for anyone who installs the service without
  `.[dense]`.
- **DENSE-INSTALL number = the dense arm.** The headline dense-lift claim is
  scoped explicitly to `.[dense]` deployments — it does NOT automatically
  apply to a default install.

Both numbers MUST appear in the sweep's writeup.

### 7.7 Similarity distribution (memorization sanity check)

Alongside the lift numbers, surface the 07-02 nearest-neighbor bank<->corpus
similarity distribution (min/median/max cosine) so a reviewer can rule out
the dense arm "winning" via near-duplicate memorization rather than genuine
retrieval-augmented generalization.

### 7.8 Framing rule (M1)

The SOTA survey's "+21 F1" appears **only** as background motivation
(`.planning/BRIEF-nl-to-conceptual-sota.md`). The actual success bar for
this phase is: *"a positive, statistically-supported pass-rate lift on the
25-case conceptual-schema corpus (paired McNemar p < 0.05 on the gpt-4o-mini
anchor)."* Never report the success bar as "+21 F1."

### 7.9 MANUAL fold-in into `baseline.json`

Same discipline as §5 — a human-reviewed copy, never auto-regenerated in
CI. Add sibling `configs['openai-gpt4o-mini-dense']` /
`configs['openai-gpt4o-mini-bm25']` / etc. entries with the aggregate
`pass_rate`/`passed`/`total`/`cases`, `model`, `temperature`, `corpus_sha`,
and the three D-04 provenance fields:

```json
{
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_revision": "7dbbc90392e2f80f3d3c277d6e90027e55de9125",
  "sentence_transformers_version": "5.6.0"
}
```

Capture `sentence_transformers_version` at RUN TIME via
`sentence_transformers.__version__` — never hardcode it; the actual
installed version is what makes the artifact reproducible, not a pin in
`pyproject.toml`. `embedding_model`/`embedding_revision` come from the pinned
constants in `arango_query_core.nl.fewshot` (07-01).

Same secret hygiene as §6: **never commit a key or raw prompts/completions**
— only the aggregate numbers + provenance cross into `baseline.json`.

---

## 8. Public-benchmark adoption (QALD-9-plus + CK25) — 07.1-06

Phase 07.1 adopted two public, human-authored NL→SPARQL benchmarks so
translation quality is measurable with real statistical power, instead of
relying only on the 25-case hand-authored `corpus.yml` (~16pt MDE). **Two
jobs, two sets (D-02/D-03) — always reported SEPARATELY, never blended
into one number (RESEARCH Pitfall 3):**

| Set | Role | Vendored corpus | Scripted config | Live config |
|-----|------|------------------|------------------|-------------|
| **QALD-9-plus** (DBpedia, CC-BY-4.0) | **Powered capability gate** — measures transferable SPARQL-generation skill (right predicates, OPTIONAL/aggregation/paths) | `vendored/qald9plus/corpus.yml` | `scripted-qald9plus` | `openai-gpt4o-mini-qald9plus` |
| **CK25** (corporate/product KG, CC-BY-4.0) | **Corporate-domain relevance anchor** — directional, NOT a power gate (small N is expected/acceptable) | `vendored/ck25/corpus.yml` | `scripted-ck25` | `openai-gpt4o-mini-ck25` |

Both sets are wired in via the additive `corpus:` config-key (§Pattern 1 of
`07.1-RESEARCH.md`) — `configs.yml`'s `corpus:` entry selects a different
`corpus.yml` than the hand-authored root file; `runner.py` needed exactly
one additive line (`config.get("corpus", "corpus.yml")`), no judge/pipeline
surgery.

### 8.1 Vendoring + provenance

Each set lives under `tests/nl2sparql/eval/vendored/{qald9plus,ck25}/` with:
`NOTICE.md` (CC-BY-4.0 attribution + source URL/commit), `raw/` (pruned
English-only / verbatim source files), `convert_{qald,ck25}.py` (the D-06
filter: parse via rdflib + judgeable + transpile to non-empty AQL + only
schema terms in the authored subset), the output `corpus.yml`
(`ontology:` + `cases:`), and `filter_log.md` (kept/dropped counts +
per-reason breakdown — D-06's "no silent truncation" audit trail).

### 8.2 Per-set scripted numbers (no-network, judge/harness plumbing only)

Run (no network, no key):

```bash
RUN_EVAL=1 python -c "from tests.nl2sparql.eval.runner import run; print(run('scripted-qald9plus').pass_rate); print(run('scripted-ck25').pass_rate)"
```

The `scripted-*` pass_rate is **1.0 for both sets** — the scripted client
replays the gold `expected` SPARQL verbatim as the "generated" response, so
a correctly-functioning judge/harness pipeline must reproduce the gold
exactly. As with the root `scripted` config (§2), **this tests the judge,
not the model** — it is not a model-quality number.

### 8.3 Achieved MDE (D-07 power module, `power.py`)

Computed via `achieved_mde(n, pi)` (Connor 1987, α=0.05, power=0.80) over
each set's D-06 surviving-case count (`filter_log.md`'s "Kept" total):

| Set | Surviving N | achieved_mde @ π=0.20 | achieved_mde @ π=0.25 | Gate role |
|-----|------------:|------:|------:|-----------|
| QALD-9-plus (train+test combined, D-02) | 514 | 0.0553 (~5.5pt) | 0.0618 (~6.2pt) | **Powered gate** |
| CK25 (D-03) | 49 | 0.179 (~17.9pt) | 0.2001 (~20.0pt) | **Anchor, reported NOT gated** |

QALD-9-plus's combined train+test pool reaches the ≤5-8pt goal (D-02);
CK25's smaller, expert-curated set stays directional by design — its role
is to catch "good at DBpedia trivia, bad at corporate schemas," not to
detect a small regression with statistical confidence. **Do not gate CI or
promotion decisions on a CK25 McNemar/MDE result** (RESEARCH
Anti-Patterns).

### 8.4 baseline.json shape (SEPARATE, never blended)

`baseline.json`'s `configs` map carries `scripted-qald9plus` and
`scripted-ck25` as their OWN top-level entries, each with `pass_rate` /
`passed` / `total` / `cases` (the same shape as `scripted`), plus:

```json
{
  "role": "powered_gate",            // or "anchor_reported_not_gated"
  "surviving_n": 514,
  "achieved_mde": {"pi_0.20": 0.0553, "pi_0.25": 0.0618},
  "note": "..."
}
```

The `scripted` entry itself is unchanged in shape — it now simply tracks
all 34 hand-authored cases (25 original + the 9-case refusal supplement
from 07.1-03).

### 8.5 Live per-set sweep (credentials-gated, human-run)

Same discipline as §§3–7: `RUN_EVAL=1` + `NL2SPARQL_API_KEY`, out-of-band,
manual human-reviewed fold-in — never auto-regenerated in CI.

```bash
RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "from tests.nl2sparql.eval.runner import run, write_report; r=run('openai-gpt4o-mini-qald9plus'); write_report(r); print('pass_rate', r.pass_rate)"
RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "from tests.nl2sparql.eval.runner import run, write_report; r=run('openai-gpt4o-mini-ck25'); write_report(r); print('pass_rate', r.pass_rate)"
```

Fold in as sibling `configs['openai-gpt4o-mini-qald9plus']` /
`configs['openai-gpt4o-mini-ck25']` entries (aggregate `pass_rate` /
`passed` / `total` / `cases` + `model` / `temperature` / `corpus_sha`),
exactly as §5 documents for the root corpus — never touching the
`scripted-*` entries.

#### 8.5.1 Execution-graded CK25 runbook (07.2, `judge: execution`)

07.2 flipped `scripted-ck25` / `openai-gpt4o-mini-ck25` from
`judge: canonical` to **`judge: execution`** in place (D-06): both gold and
candidate SPARQL now run against the vendored CK25 instance graph
(`vendored/ck25/raw/prod-inst.ttl`) via pyoxigraph, and pass/fail is decided
by comparing the resulting **answer sets** (up to variable renaming and
`rdfs:label`↔IRI normalization), not by comparing SPARQL text. This is an
opt-in per-config setting — every other config (`scripted`,
`openai-gpt4o-mini`, `scripted-qald9plus`, `openai-gpt4o-mini-qald9plus`,
all `few_shot` configs) stays on `judge: canonical`, untouched.

Environment, same Pitfall 1 as §3 — **`NL2SPARQL_API_KEY`, NOT
`OPENAI_API_KEY`** — plus the extras this judge needs:

```bash
# dev provides pyoxigraph (the W3C-reference execution engine the judge runs
# gold + candidate SPARQL against); nl provides the openai client the live
# candidate-generation path needs. Both are required for this sweep.
uv sync --extra dev --extra nl

export NL2SPARQL_API_KEY=sk-...          # your OpenAI key — this shell only, never OPENAI_API_KEY
```

Capture the corpus revision (the vendored CK25 corpus, not the root one):

```bash
git log -1 --format=%h -- tests/nl2sparql/eval/vendored/ck25/corpus.yml
```

Run the live, execution-judged sweep. It writes
`reports/openai-gpt4o-mini-ck25.{json,md}` (**gitignored**,
`tests/nl2sparql/eval/reports/` in `.gitignore`) and prints the aggregate +
per-case verdicts, including each failing case's `judge_note` (the D-05
bucket tag, e.g. `candidate_engine_rejected: ...` / `gold_engine_limitation:
...`, or `None` for an ordinary wrong-answer mismatch):

```bash
RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "from tests.nl2sparql.eval.runner import run, write_report; r=run('openai-gpt4o-mini-ck25'); write_report(r); print('pass_rate', r.pass_rate); [print(c.name, c.passed, c.judge_note) for c in r.cases]"
```

Fold in by hand exactly as §8.5 / §5 document — a **new**, separate
`configs['openai-gpt4o-mini-ck25']` entry (never touching `scripted-ck25`
or any other entry, RESEARCH Pitfall 4), carrying `pass_rate` / `passed` /
`total` / `cases` + `model: "gpt-4o-mini"` / `temperature: 0.1` /
`corpus_sha`, plus:

- `role: "anchor_reported_not_gated"` — this number is **reported, not
  gated**: at N=49 the achieved MDE is ~18-20pt (§8.3), too small to detect
  a regression with statistical confidence, so it must never be wired into
  a CI gate or a promotion decision (D-07).
- A `note` recording the **D-05 buckets distinctly** — the count of failing
  cases whose `judge_note` starts `candidate_engine_rejected` and the count
  starting `gold_engine_limitation` — so engine-side rejections are never
  silently blended into ordinary wrong-answer failures (RESEARCH Pitfall 3).
- The same `rdfs:label` collision caveat as `scripted-ck25`'s note (Open
  Q1): `Hardware` 1000/837 = 163 collisions, `Supplier` 250/246 = 4
  collisions, all other entity classes 1:1 — a documented, non-gating
  residual risk of the execution judge's label-based normalization.

This is a **human checkpoint, not a CI step**: the sweep needs
`NL2SPARQL_API_KEY`, which the agent/CI must never hold, and the fold-in
into `baseline.json` is always a manual, human-reviewed copy — CI never
auto-regenerates it (same discipline as §5/§7.9).

### 8.6 Non-regression invariants (unchanged)

- `scripted` remains the sole CI-reachable config
  (`test_ci_gate_only_ever_runs_scripted`); every new `scripted-*` config is
  still only reachable by explicit `run("scripted-...")` calls, never from
  the default test path.
- W3C DAWG `QUERY_EVAL` coverage stays ≥ 96.4%
  (`tests/w3c/test_coverage_gate.py`) — the transpiler is untouched by this
  phase.
- No secrets, raw prompts/completions, or full multilingual JSON blobs are
  vendored — only the CC-BY-4.0-licensed English question/gold-SPARQL pairs
  the harness needs, plus the required attribution `NOTICE.md` per set.

---

## 9. CK25 entity/instance grounding sweep — NL-ACC-01 (Phase 07.3)

This section documents the credentialed, human-run measurement behind
NL-ACC-01: does injecting retrieved instance IRIs+labels ("Known entities —
use these EXACT IRIs") for entities named in the question produce a
**statistically significant** execution-graded pass-rate lift on CK25 over a
freshly-run zero-shot arm? Same discipline as §§3–6 and §8.5.1 (key-gated,
`scripted` stays the CI default, manual human-reviewed fold-in), with one
addition specific to grounding: the confirmatory comparison is always
**grounded-vs-a-fresh-zero-arm run in the SAME session**, never grounded vs
the already-committed `openai-gpt4o-mini-ck25` baseline entry — that entry
was captured in a prior session (07.2-04) and model drift across sessions is
a real confound (RESEARCH Pitfall / 07-04 M2), exactly the same discipline
§7.2 established for the dense few-shot sweep.

### 9.1 Design

Both arms use `judge: execution` (07.2's answer-set judge against the
vendored CK25 instance graph) and share the same model/temperature:

- **`openai-gpt4o-mini-ck25`** — the fresh zero arm. Re-run THIS session
  (not read from the already-committed `baseline.json` entry).
- **`openai-gpt4o-mini-ck25-grounded`** — the grounded arm. Seam 6
  (`grounding_index` / `GroundedEntity`, wired through the eval runner in
  Plan 07.3-05) retrieves top-k label-matched instance IRIs per question and
  injects them into the prompt; everything else (model, temperature, corpus,
  judge) is identical to the zero arm.

### 9.2 Temperature provenance (Plan 07.3-06 Task 1)

`OpenAICompatibleClient` has no `configs.yml` temperature override path —
`runner.py::_client_for()` never passes `temperature=`, so both
`openai-gpt4o-mini-ck25` and `openai-gpt4o-mini-ck25-grounded` run at the
constructor's hardcoded default `temperature=0.1` (same value already
recorded on the committed `openai-gpt4o-mini-ck25` entry), **not** the
07.3 pre-planning spike's explicit `temperature=0`
(`grounding_spike.py` hardcoded 0 in its raw HTTP call). A non-reproduction
of the spike's exact 6/49→12/49 numbers is therefore attributable to this
temperature delta, not to grounding failing (RESEARCH Open Question 1,
resolved) — record `"temperature": 0.1` in the fold-in, not the spike's 0.

### 9.3 Run both arms in ONE session

```bash
uv sync --extra dev --extra nl   # dev: pyoxigraph judge; nl: openai client
export NL2SPARQL_API_KEY=sk-...  # your OpenAI key — this shell only, never OPENAI_API_KEY (Pitfall 1)
```

Capture the vendored CK25 corpus revision:

```bash
git log -1 --format=%h -- tests/nl2sparql/eval/vendored/ck25/corpus.yml
```

Run both arms fresh, THIS session, then compute the paired McNemar test and
bootstrap delta over the same 49 cases:

```bash
RUN_EVAL=1 NL2SPARQL_API_KEY=... python -c "
from tests.nl2sparql.eval.runner import run, write_report, paired_mcnemar, bootstrap_paired_delta

zero = run('openai-gpt4o-mini-ck25')            # freshly run THIS session
grounded = run('openai-gpt4o-mini-ck25-grounded')
write_report(zero)
write_report(grounded)

zero_cases = {c.name: c.passed for c in zero.cases}
grounded_cases = {c.name: c.passed for c in grounded.cases}

print('zero pass_rate', zero.pass_rate)
print('grounded pass_rate', grounded.pass_rate)
b, c, p = paired_mcnemar(zero_cases, grounded_cases)
delta, lo, hi = bootstrap_paired_delta(zero_cases, grounded_cases)
print(f'b={b} c={c} p={p:.4f} delta={delta:.4f} CI=({lo:.4f}, {hi:.4f})')
"
```

Writes `reports/openai-gpt4o-mini-ck25.{json,md}` and
`reports/openai-gpt4o-mini-ck25-grounded.{json,md}` (both **gitignored**).

**The lift PASSES iff McNemar `p < 0.05` with zero regressions (`c=0` or a
non-negative net flip count)** — this is THE confirmatory bar for NL-ACC-01,
mirroring §7.3's dense/zero bar exactly. Report `b`, `c`, the exact p-value,
the bootstrap paired-delta 95% CI, and the per-case gained/regressed case
names.

### 9.4 MANUAL fold-in into `baseline.json` (never CI-auto-regenerated)

Same discipline as §5/§7.9/§8.5 — a human-reviewed copy. Add a **new**,
separate `configs['openai-gpt4o-mini-ck25-grounded']` entry (never touching
`scripted-ck25` or the existing `openai-gpt4o-mini-ck25` entry — RESEARCH
Pitfall 4/3) carrying the aggregate `pass_rate`/`passed`/`total`/`cases` +
`model: "gpt-4o-mini"` / `temperature: 0.1` / `corpus_sha`, plus:

- `role: "anchor_reported_not_gated"` — same N=49 achieved-MDE caveat as
  `openai-gpt4o-mini-ck25` (§8.3): never gate CI or a promotion decision on
  this pass_rate alone.
- A `confirmatory_test` object recording the fresh zero arm's pass_rate,
  `b`/`c`/`p_value`, the bootstrap `paired_delta`/`ci_95`, the
  `gained_0_to_1`/`regressed_1_to_0` case-name lists, and the
  `nl_acc_01_disposition` (significant-lift vs documented-null — mirror the
  `phase07_dense_few_shot_sweep.primary_confirmatory_test` shape in §7.9).
- If Task 2's live sweep instead returns a null/inconclusive result, record
  it via the documented-null path (mirroring NL-FEW-02, §7.3) — never claim
  a passed confirmatory test that didn't clear `p < 0.05`.

Same secret hygiene as §6: never commit a key or raw prompts/completions —
only aggregate numbers + provenance cross into `baseline.json`.

### 9.5 Non-regression (unchanged, re-confirm before closing NL-ACC-01)

- `pytest tests/w3c/test_coverage_gate.py -q` green (QUERY_EVAL ≥ 96.4%) or
  skips key-free when the W3C corpus isn't fetched locally.
- `git diff --stat -- arango_sparql/translate/` empty across every phase
  commit — the transpiler is untouched by NL-ACC-01.
- `scripted`/`scripted-ck25` remain the only CI-reachable configs
  (`test_ci_gate_only_ever_runs_scripted`); the grounded config is reachable
  only via an explicit, human-run `run("openai-gpt4o-mini-ck25-grounded")`
  call, never from the default test path.

### 9.6 Post-review builder correction + clean-builder re-sweep (07.3-REVIEW.md CR-01/CR-02)

Code review (`07.3-REVIEW.md`) of this phase found 2 **blocker-level** bugs in
`tests/nl2sparql/eval/grounding_index_builder.py` — the eval-only helper that
built the `LabelIndex` behind the §9 sweep above — neither caught by the
existing recall-only test:

- **CR-01** — `build_label_index()`'s SPARQL query had no filter excluding
  ontology-level subjects, so CK25's OWL vocabulary header (classes/
  properties, each carrying its own `rdfs:label`) leaked into the "Known
  entities" prompt block as if they were groundable instances: 45/2618
  indexed "entities" were schema terms, retrieved by 43/49 (88%) of CK25
  questions.
- **CR-02** — label-literal stripping stripped quotes *before* splitting off
  the `^^<datatype>`/`@lang` suffix, corrupting every language-tagged label
  (e.g. `"Manager"@en` → `'Manager"@en'` instead of `'Manager'`) that
  survived verbatim into the LLM prompt.

Both were **fixed** (commits `f932360` CR-01, `6c72b37` CR-02): the index
now excludes `owl:Class`/`owl:ObjectProperty`/`owl:DatatypeProperty`/
`owl:AnnotationProperty`/`rdf:Property`/`rdfs:Class`/`owl:Ontology`/
`void:Dataset`-typed subjects plus structurally-schema subjects (used as an
`rdf:type` object or as a predicate anywhere), and label normalization now
mirrors `runner.py::_strip_execution_literal`'s split-then-strip order.
Verified against the real vendored CK25 corpus: index size drops
2618 → 2573 (the 45 schema terms), zero entities carry a stray `"` in their
label, and the offline recall guard (`test_grounding_recall.py`) still
passes at 0.96 (≥ the 0.90 spike floor).

The full §9.3 grounded-vs-fresh-zero same-session sweep was **re-run in
full on the corrected builder**. Result — the aggregate reproduces
**identically**: 14/49 (28.6%) grounded vs 5/49 (10.2%) fresh zero,
McNemar b=9/c=0/p=0.0039, bootstrap paired delta +0.1837 (95% CI
[0.0816, 0.3061]) — but the per-case **gained-case set shifted**: the
pre-fix sweep gained `ck25-9`/`ck25-46`; the clean-builder sweep instead
gained `ck25-10`/`ck25-11` (both sets still 9 cases, still zero
regressions). This is the headline evidence: removing the schema-IRI
noise and the label corruption did **not** inflate or manufacture the
measured lift — the same conclusion holds on a demonstrably cleaner index.

`baseline.json`'s `openai-gpt4o-mini-ck25-grounded` entry (`cases` map and
`confirmatory_test.gained_0_to_1`) has been updated in place to these
clean-builder values, superseding the pre-fix per-case data; the full
before/after comparison is recorded in
`confirmatory_test.clean_builder_reconfirmation`. NL-ACC-01 remains closed
via the significant-lift path — this re-sweep *strengthens*, not weakens,
that disposition.
