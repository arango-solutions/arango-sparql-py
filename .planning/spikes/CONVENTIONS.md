# Spike Conventions

Patterns established across spike sessions. New spikes follow these unless the
question requires otherwise.

## Stack

- **Python via `uv run`** — the project venv (`.venv`) has the package + `[dev,nl]`
  extras. Plain `python` misses `arango_sparql`; always `uv run python …`.
- **pyoxigraph** as the execution oracle — load the corpus `data_path` ttl into an
  `oxi.Store` and query it via `tests/helpers/oxi.py::oxi_query`. This is the SAME
  engine the eval harness's execution judge uses, so offline verification matches
  live grading.
- **Real transpiler for validity** — `arango_sparql.api.translate(query,
  resolver=SchemaResolver.from_turtle(ontology))`; non-empty `.aql` == judgeable.

## Structure

- One directory per spike: `.planning/spikes/NNN-descriptive-name/`.
- A `verify_*.py` no-LLM gate (parse + transpile + execute-non-empty) proves the
  authored SPARQL is valid before any credentialed run.
- A `run_spike.py` with a **`--dry-run` (no key)** mode and a **`--sweep` (human
  key)** mode.

## Patterns

- **Isolation via monkeypatch, not edits.** Drive the real eval runner without
  touching production files: monkeypatch `runner._load_configs` to inject a spike
  arm and reassign `runner.BANK_PATH`; `runner.cached_few_shot_index.cache_clear()`
  between arms. `configs.yml` / `runner.py` / `fewshot_bank.yml` stay unmodified.
- **Human-run credentialed sweeps.** The agent never holds `NL2SPARQL_API_KEY`.
  Live arms are gated behind `RUN_EVAL=1` + the key; the spike builds to the
  checkpoint and the human runs `--sweep`.
- **Paired same-session comparison.** Compare a new arm against a *fresh* zero arm
  run in the same session (never a stale committed baseline number); report
  `paired_mcnemar` (b=gains, c=regressions) + `bootstrap_paired_delta`.
- **Leakage-safe examples.** Same shape as the target, entity-disjoint on entity
  AND query-shape axes (D-05); verify algebra-disjointness from the held-out golds
  in the offline gate.

## Tools & Libraries

- `pyoxigraph` 0.5.x, `rank_bm25` (both in the `[dev,nl]` extras).
- `arango_query_core.nl.FewShotIndex` / `cached_few_shot_index` — bank consumption
  via BM25; corpus-file shape is `version:` + `examples:` list of
  `{question, query}`.
