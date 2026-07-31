"""Verify the thin spike bank WITHOUT any LLM / network.

For each example: (a) parses via rdflib, (b) transpiles to non-empty AQL via
the real transpiler, (c) executes non-empty against prod-inst.ttl (pyoxigraph
== the eval judge's engine). For the top-N examples, additionally assert the
extremum is STRICTLY unique (rank-1 value > rank-2 value) so LIMIT 1 is
deterministic and the example's stated answer is unambiguous.

Also runs a leakage guard: every example's canonical algebra must DIFFER from
every held-out CK25 gold's canonical algebra (same shape is fine and intended;
an identical query would be leakage).

Run:  python .planning/spikes/001-ck25-thin-fewshot-signal/verify_bank.py
Exit 0 == all green.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from arango_sparql.api import translate
from arango_sparql.translate.resolver import SchemaResolver
from tests.helpers.oxi import oxi_query
from tests.nl2sparql.eval.runner import _canonical, _load_corpus

SPIKE_DIR = Path(__file__).resolve().parent
BANK = SPIKE_DIR / "ck25_thin_fewshot_bank.yml"
CK25 = Path("tests/nl2sparql/eval/vendored/ck25/corpus.yml")
DATA = Path("tests/nl2sparql/eval/vendored/ck25/raw/prod-inst.ttl")

import pyoxigraph as oxi

# --- top-N examples that must have a strictly-unique extremum, with the
#     value-bearing "probe" query (drop the LIMIT, order desc, read top 2) ---
TOPN_PROBES = {
    "What is the most expensive Resistor we offer?": """
        PREFIX pv: <http://ld.company.org/prod-vocab/>
        SELECT ?amount WHERE {
          ?category pv:name "Resistor" .
          ?r pv:hasCategory ?category .
          ?r pv:price ?p . ?p pv:amount ?amount .
        } ORDER BY DESC(?amount) LIMIT 2
    """,
    "Which Rheostat is the widest?": """
        PREFIX pv: <http://ld.company.org/prod-vocab/>
        SELECT ?width WHERE {
          ?category pv:name "Rheostat" .
          ?r pv:hasCategory ?category .
          ?r pv:width_mm ?width .
        } ORDER BY DESC(?width) LIMIT 2
    """,
    "Which supplier delivers the most reliable Gauge?": """
        PREFIX pv: <http://ld.company.org/prod-vocab/>
        SELECT ?ri WHERE {
          ?category pv:name "Gauge" .
          ?hw pv:hasCategory ?category .
          ?hw pv:reliabilityIndex ?ri .
        } ORDER BY DESC(?ri) LIMIT 2
    """,
}


def main() -> int:
    bank = yaml.safe_load(BANK.read_text())
    examples = bank["examples"]

    ck25 = _load_corpus(CK25)
    ontology_ttl = ck25["ontology"]
    resolver = SchemaResolver.from_turtle(ontology_ttl)

    store = oxi.Store()
    store.load(DATA.read_bytes(), oxi.RdfFormat.TURTLE)

    # Held-out canonical algebras for the leakage guard.
    held_out_canon = set()
    for case in ck25["cases"]:
        c = _canonical(case["expected"])
        if c is not None:
            held_out_canon.add(c)

    ok = True
    print(f"Verifying {len(examples)} examples\n" + "=" * 60)
    for i, ex in enumerate(examples, 1):
        q = ex["question"]
        query = ex["query"]
        tag = f"[{i}] {q}"

        # (a) parses
        canon = _canonical(query)
        if canon is None:
            print(f"FAIL parse   {tag}")
            ok = False
            continue

        # leakage guard: canonical algebra must not equal a held-out gold's
        if canon in held_out_canon:
            print(f"FAIL leakage {tag}  (identical algebra to a held-out gold)")
            ok = False

        # (b) transpiles to non-empty AQL
        try:
            result = translate(query, resolver=resolver)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL transpile {tag}  ({type(exc).__name__}: {exc})")
            ok = False
            continue
        if not result.aql:
            print(f"FAIL transpile {tag}  (EMPTY AQL)")
            ok = False
            continue

        # (c) executes non-empty
        res = oxi_query(store, query)
        nrows = len(res.rows or [])
        if nrows == 0:
            print(f"FAIL empty   {tag}  (0 rows)")
            ok = False
            continue

        # (d) top-N strict-uniqueness
        extra = ""
        if q in TOPN_PROBES:
            probe = oxi_query(store, TOPN_PROBES[q])
            vals = [list(r.values())[0] for r in (probe.rows or [])]
            v = [float(x.split("^^")[0].strip('"')) for x in vals]
            if len(v) < 2:
                extra = f"  top-N: only {len(v)} value(s) — trivially unique"
            elif v[0] <= v[1]:
                print(f"FAIL tie     {tag}  (rank1={v[0]} <= rank2={v[1]})")
                ok = False
                continue
            else:
                extra = f"  top-N unique: rank1={v[0]} > rank2={v[1]}"

        print(f"OK  {tag}  -> {nrows} row(s){extra}")

    print("=" * 60)
    print("ALL GREEN" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
