"""gpt-5-mini extraction-vs-capability diagnostic (2026-08) — HUMAN-run.

The 07-04 3-model sweep had gpt-5-mini UNDER gpt-4o-mini on NL->SPARQL
(bm25 0.44 vs 0.568). Two explanations are indistinguishable from the aggregate
number: (a) a genuine reasoning/capability gap, or (b) a plumbing artifact —
gpt-5-family "reasoning" models emit a thinking preamble, and if the SPARQL
extractor (`extract_sparql_from_response`) doesn't cleanly strip it, a CORRECT
query is mis-parsed and scored as a failure.

This runs gpt-5-mini on a handful of genuine-composition bucket-1 cases (the
analytic failures gpt-4o-mini can't do — superlative-over-category, count,
grouped-superlative, negation) and prints, per case, the RAW model output next
to the EXTRACTED SPARQL and the execution verdict, so the failure mode is
visible. It classifies each via the judge's own note:

  CORRECT                         judge passed
  EXTRACTION / PARSE-FAIL         candidate rejected by the engine (parse/exec
                                  error) -- the (b) plumbing hypothesis; inspect
                                  the raw output for un-stripped preamble
  WRONG-QUERY                     parsed + executed, wrong answer -- the (a)
                                  capability hypothesis
  INCONCLUSIVE                    the gold itself errors in pyoxigraph

If the failures cluster on EXTRACTION, fix the extractor before trusting any
gpt-5-mini number. If they cluster on WRONG-QUERY, gpt-5-mini genuinely does not
help these cases and the 07-04 regression stands.

Usage
-----
  # offline sanity check (no key, no network) — builds the setup only:
  .venv/bin/python tests/nl2sparql/eval/gpt5_mini_diagnostic.py --check

  # the real diagnostic (needs the human key):
  RUN_EVAL=1 NL2SPARQL_API_KEY=... .venv/bin/python tests/nl2sparql/eval/gpt5_mini_diagnostic.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
os.chdir(REPO)

CONFIG = "openai-gpt5-mini-ck25-grounded-analytic-fewshot"
# genuine-composition bucket-1 cases (NOT the country-convention / ambiguous /
# judge-artifact ones — those are not model-quality problems): superlative-over-
# category, count+multi-constraint, grouped-superlative, negation.
SELECTED = ["ck25-9", "ck25-21", "ck25-25", "ck25-33", "ck25-40", "ck25-46"]


class _CaptureClient:
    """Delegates to a real LLM client but tees every raw completion so the
    diagnostic can compare raw output against the extracted SPARQL."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.raws: list[str] = []

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        resp = self._inner.generate(*args, **kwargs)
        self.raws.append(getattr(resp, "content", repr(resp)))
        return resp

    def __getattr__(self, name: str) -> Any:  # delegate everything else
        return getattr(self._inner, name)


def _build() -> tuple[dict, dict, Any, int, Any, int, str | None, str]:
    """Replicate runner.run()'s per-arm setup for CONFIG (no per-case loop)."""
    from tests.nl2sparql.eval.runner import (
        BANK_PATH,
        EVAL_DIR,
        _load_configs,
        _load_corpus,
        cached_few_shot_index,
    )

    config = _load_configs()["configs"][CONFIG]
    corpus_path = EVAL_DIR / config.get("corpus", "corpus.yml")
    corpus = _load_corpus(corpus_path)
    shared_ontology = corpus.get("ontology", "")
    max_repairs = config.get("max_repairs", 2)
    data_path = corpus.get("data_path")
    data_ttl = (corpus_path.parent / data_path).read_text() if data_path else None

    fs = config.get("few_shot", {})
    few_shot_k = fs.get("k", 0)
    bank_path = EVAL_DIR / fs["bank"] if fs.get("bank") else BANK_PATH
    few_shot_index = (
        cached_few_shot_index(str(bank_path), fs["mode"]) if fs.get("mode") in ("dense", "bm25") else None
    )

    gc = config.get("grounding", {})
    grounding_k = gc.get("k", 0)
    grounding_index = None
    if gc and data_ttl:
        from tests.nl2sparql.eval.grounding_index_builder import build_label_index

        grounding_index = build_label_index(
            data_ttl, gc.get("label_predicates", ["rdfs:label"]), prefixes=gc.get("prefixes")
        )

    cases_by_name = {c["name"]: c for c in corpus["cases"]}
    return (
        config,
        cases_by_name,
        few_shot_index,
        few_shot_k,
        grounding_index,
        grounding_k,
        data_ttl,
        shared_ontology,
    )


def check() -> int:
    """Offline: build the setup, confirm indices + selected cases, no model call."""
    cfg, cases, fs_idx, fs_k, gr_idx, gr_k, data_ttl, onto = _build()
    print("=" * 70)
    print(f"CHECK (offline, no model call) — config {CONFIG!r}")
    print("=" * 70)
    print(f"  model         : {cfg['provider'].get('model')}")
    print(f"  few_shot_index: {type(fs_idx).__name__} (k={fs_k})")
    print(f"  grounding_index: {'built' if gr_idx else 'none'} (k={gr_k})")
    print(f"  data_ttl      : {'loaded' if data_ttl else 'none'}")
    missing = [c for c in SELECTED if c not in cases]
    print(f"  selected cases: {SELECTED}  {'(all present)' if not missing else f'MISSING {missing}'}")
    print("\nCHECK OK — setup builds. Run with RUN_EVAL=1 + NL2SPARQL_API_KEY for the live diagnostic.")
    return 0 if not missing else 1


def diagnose() -> int:
    if os.getenv("RUN_EVAL", "").strip().lower() in ("", "0", "false", "no"):
        print("ERROR: set RUN_EVAL=1 to run the live diagnostic.", file=sys.stderr)
        return 2
    if not os.getenv("NL2SPARQL_API_KEY"):
        print("ERROR: NL2SPARQL_API_KEY must be set (human-held key).", file=sys.stderr)
        return 2

    from arango_sparql.errors import SparqlParseError
    from arango_sparql.nl2sparql import NlPipeline
    from arango_sparql.translate.parser import parse_sparql
    from arango_sparql.translate.resolver import SchemaResolver
    from tests.nl2sparql.eval.runner import _client_for, _judge

    cfg, cases, fs_idx, fs_k, gr_idx, gr_k, data_ttl, onto = _build()
    judge_name = cfg.get("judge", "execution")
    max_repairs = cfg.get("max_repairs", 2)

    tally: dict[str, int] = {}
    for cid in SELECTED:
        case = cases[cid]
        ontology_ttl = case.get("ontology", onto)
        resolver = SchemaResolver.from_turtle(ontology_ttl)
        client = _CaptureClient(_client_for(cfg, case))
        pipeline = NlPipeline(
            client=client,
            resolver=resolver,
            ontology_ttl=ontology_ttl,
            max_repairs=max_repairs,
            few_shot_k=fs_k,
            few_shot_index=fs_idx,
            grounding_k=gr_k,
            grounding_index=gr_idx,
        )
        outcome = pipeline.run(case["nl"], params=case.get("params"))
        passed, note = _judge(judge_name, case, outcome, data_ttl)

        try:
            parse_sparql(outcome.sparql)
            parses = True
        except SparqlParseError:
            parses = False

        if passed:
            verdict = "CORRECT"
        elif note and note.startswith("candidate_engine_rejected"):
            verdict = "EXTRACTION / PARSE-FAIL (candidate rejected by engine)"
        elif note and note.startswith("gold_engine_limitation"):
            verdict = "INCONCLUSIVE (gold errors in pyoxigraph)"
        else:
            verdict = "WRONG-QUERY (parsed + ran, wrong answer)"
        tally[verdict] = tally.get(verdict, 0) + 1

        raw = client.raws[-1] if client.raws else ""
        has_fence = "```sparql" in raw or "```" in raw
        print("=" * 70)
        print(f"{cid}: {case['nl']}")
        print(f"  attempts={len(client.raws)}  fence_in_raw={has_fence}  extracted_parses={parses}")
        print(f"  judge: passed={passed} note={note!r}")
        print(f"  >>> VERDICT: {verdict}")
        print("  --- RAW (final completion, first 700 chars) ---")
        print("  " + raw[:700].replace("\n", "\n  "))
        print("  --- EXTRACTED SPARQL ---")
        print("  " + (outcome.sparql or "(empty)").strip()[:500].replace("\n", "\n  "))
        print()

    print("=" * 70)
    print("SUMMARY")
    for v, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {n}  {v}")
    print("=" * 70)
    print(
        "Read: EXTRACTION/PARSE-FAIL clustering => fix the extractor before trusting gpt-5-mini.\n"
        "      WRONG-QUERY clustering => genuine capability gap; the 07-04 regression stands."
    )
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="offline setup check (no key, no model call)")
    args = ap.parse_args()
    raise SystemExit(check() if args.check else diagnose())
