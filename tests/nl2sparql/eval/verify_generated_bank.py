"""Ontology-parameterized offline validity gate for a generated few-shot
bank (Phase 07.5 Stage 1, D-01/D-04).

Promotes the VALIDATED spike gate
(``.planning/spikes/001-ck25-thin-fewshot-signal/verify_bank.py``) from
three hardcoded CK25 module constants to a reusable
``verify_bank(bank_path, corpus_path, data_path=None) -> int`` function
(plus an argparse CLI), so any future ``<ontology>_fewshot_bank.yml`` the
generator emits (CK25, QALD, ...) can be gated by the same code path.

For each example: (a) parses via rdflib (REQ-1), (b) transpiles to
non-empty AQL via the real transpiler (REQ-1), and -- unless *data_path*
is omitted -- (c) executes non-empty against the source instance data
(REQ-2), using pyoxigraph (the same engine the execution judge uses).
For ranking-shape examples carrying an optional per-example ``probe``
field, additionally asserts the extremum is STRICTLY unique (rank-1 value
> rank-2 value) so ``LIMIT 1``/``OFFSET 1`` is deterministic.

**TBox-only structural mode (D-04):** when *data_path* is ``None`` (e.g.
QALD, which has no rich instance snapshot), step (c) and the
strict-extremum probe are skipped -- only parse+transpile validity is
checked (REQ-1's structural half). This is the documented degrade path
for a data-less ontology, not a silent skip.

Also runs a leakage guard (unchanged from the spike): every example's
canonical algebra must DIFFER from every held-out corpus gold's canonical
algebra (same shape is fine and intended; an identical query is leakage).

And a name-anchoring guard (Pitfall 3 / spike carry-forward #1): a
generated query must reference only the ontology's OWN declared
vocabulary namespace(s) (+ the well-known RDF/RDFS/OWL/XSD namespaces,
e.g. ``rdfs:label``) -- never a hardcoded instance-namespace IRI (CK25's
``prodi:``). The allowed vocabulary namespace(s) are derived MECHANICALLY
from which namespace(s) the ontology's own ``owl:Class``/
``owl:ObjectProperty``/``owl:DatatypeProperty`` declarations live in --
never a hand-picked prefix name (D-02 discipline, generalizes to any
ontology).

Packaging boundary (CLAUDE.md hard rule 5 / D-08): this file MUST live
under ``tests/`` and MUST NOT be imported by
``arango_query_core``/``arango_sparql`` proper. Every ``pyoxigraph``-
touching import stays function-local (never at module top level).

Run:  uv run python tests/nl2sparql/eval/verify_generated_bank.py \\
        --bank <path> --corpus <path> [--data <path>]
Exit 0 == all green.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Well-known W3C RDF vocabulary namespaces -- dataset-INDEPENDENT (never a
# per-schema hint); always allowed in a name-anchored query alongside the
# ontology's own declared vocabulary namespace(s).
_WELL_KNOWN_NAMESPACES = frozenset(
    {
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2002/07/owl#",
        "http://www.w3.org/2001/XMLSchema#",
    }
)


def _schema_namespaces(ontology_ttl: str) -> set[str]:
    """The set of namespace URIs used as the SUBJECT of an
    ``owl:Class``/``owl:ObjectProperty``/``owl:DatatypeProperty``
    declaration in *ontology_ttl* -- i.e. the ontology's own vocabulary
    namespace(s), derived STRUCTURALLY (never a hand-picked prefix name)
    so the name-anchoring guard below generalizes to any ontology (D-02
    discipline)."""
    from tests.helpers.oxi import load_store_from_string, oxi_query

    store = load_store_from_string(ontology_ttl)
    query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT DISTINCT ?s WHERE {
      { ?s a owl:Class } UNION { ?s a owl:ObjectProperty } UNION { ?s a owl:DatatypeProperty }
    }"""
    namespaces: set[str] = set()
    for row in oxi_query(store, query).rows or []:
        term = row.get("s") or ""
        iri = term[1:-1] if term.startswith("<") and term.endswith(">") else term
        if not iri:
            continue
        namespaces.add(iri.rsplit("#", 1)[0] + "#" if "#" in iri else iri.rsplit("/", 1)[0] + "/")
    return namespaces


def _query_prefixes(query: str) -> dict[str, str]:
    """Extract ``PREFIX foo: <...>`` declarations from a SPARQL query body."""
    return dict(re.findall(r"PREFIX\s+(\w*):\s*<([^>]+)>", query, flags=re.IGNORECASE))


def _contains_instance_namespace_iri(query: str, allowed_namespaces: set[str]) -> bool:
    """True if *query* references any IRI (bare ``<...>`` or ``prefix:local``)
    whose namespace falls OUTSIDE *allowed_namespaces* union the well-known
    RDF/RDFS/OWL/XSD namespaces.

    Per RESEARCH Pitfall 3: a name-anchored generated query must reference
    ONLY the ontology's vocabulary predicates/classes (+ well-known RDF
    vocabulary like ``rdfs:label``) -- never a hardcoded instance-namespace
    IRI (CK25's ``prodi:``). Literals (``"..."``) and SPARQL variables
    (``?x``) are never matched by the IRI-shaped patterns below, so a
    name-anchored ``?d pv:name "Engineering"`` triple passes cleanly.
    """
    allowed = allowed_namespaces | _WELL_KNOWN_NAMESPACES
    for match in re.finditer(r"<(http[^>]+)>", query):
        iri = match.group(1)
        if not any(iri.startswith(ns) for ns in allowed):
            return True
    prefixes = _query_prefixes(query)
    body = re.sub(r"PREFIX\s+\w*:\s*<[^>]+>", "", query, flags=re.IGNORECASE)
    for match in re.finditer(r"(?<![:<\w])(\w+):(\w[\w-]*)", body):
        prefix = match.group(1)
        namespace = prefixes.get(prefix)
        if namespace is None:
            continue
        if not any(namespace.startswith(ns) or ns.startswith(namespace) for ns in allowed):
            return True
    return False


def _strict_extremum_ok(store: Any, probe: str) -> tuple[bool, str]:
    """Run *probe* (drop-LIMIT / ORDER BY DESC / top-2 SPARQL, generator- or
    bank-authored) and require the extremum be STRICTLY unique
    (rank1 > rank2) so ``LIMIT 1``/``OFFSET 1`` is deterministic. Returns
    ``(ok, message)``."""
    from tests.helpers.oxi import oxi_query

    probe_result = oxi_query(store, probe)
    values = [list(row.values())[0] for row in (probe_result.rows or [])]
    parsed = [float(v.split("^^")[0].strip('"')) for v in values]
    if len(parsed) < 2:
        return True, f"probe: only {len(parsed)} value(s) — trivially unique"
    if parsed[0] <= parsed[1]:
        return False, f"rank1={parsed[0]} <= rank2={parsed[1]}"
    return True, f"probe unique: rank1={parsed[0]} > rank2={parsed[1]}"


def verify_bank(
    bank_path: Path | str,
    corpus_path: Path | str,
    data_path: Path | str | None = None,
) -> int:
    """Verify every example in *bank_path* against *corpus_path*'s ontology
    (+ optional *data_path* instance data). Returns ``0`` if every example
    is valid, ``1`` otherwise (spike's exit convention, unchanged)."""
    from arango_sparql.api import translate
    from arango_sparql.translate.resolver import SchemaResolver
    from tests.helpers.oxi import oxi_query
    from tests.nl2sparql.eval.runner import _canonical, _load_corpus

    bank_path = Path(bank_path)
    corpus_path = Path(corpus_path)

    bank = yaml.safe_load(bank_path.read_text())
    examples = bank.get("examples", [])

    corpus = _load_corpus(corpus_path)
    ontology_ttl = corpus["ontology"]
    resolver = SchemaResolver.from_turtle(ontology_ttl)
    allowed_namespaces = _schema_namespaces(ontology_ttl)

    structural_only = data_path is None
    store = None
    if not structural_only:
        import pyoxigraph as oxi

        data_path = Path(data_path)
        store = oxi.Store()
        store.load(data_path.read_bytes(), oxi.RdfFormat.TURTLE)

    # Leakage guard: held-out canonical algebras (unchanged from the spike).
    held_out_canon: set[str] = set()
    for case in corpus.get("cases", []):
        if case.get("expect_refusal"):
            continue
        canon = _canonical(case["expected"])
        if canon is not None:
            held_out_canon.add(canon)

    ok = True
    mode = "structural (TBox-only, no --data)" if structural_only else "full (data-bound)"
    print(f"Verifying {len(examples)} examples [{mode}]\n" + "=" * 60)
    for i, example in enumerate(examples, 1):
        question = example["question"]
        query = example["query"]
        tag = f"[{i}] {question}"

        # name-anchoring guard (Pitfall 3, spike carry-forward #1)
        if _contains_instance_namespace_iri(query, allowed_namespaces):
            print(f"FAIL name-anchor {tag}  (query references an instance-namespace IRI)")
            ok = False
            continue

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

        if structural_only:
            print(f"OK  {tag}  -> parses+transpiles (structural mode)")
            continue

        # (c) executes non-empty
        res = oxi_query(store, query)
        nrows = (1 if res.boolean else 0) if res.kind == "ask" else len(res.rows or [])
        if nrows == 0:
            print(f"FAIL empty   {tag}  (0 rows)")
            ok = False
            continue

        # (d) optional per-example strict-extremum probe (ranking shapes)
        extra = ""
        probe = example.get("probe")
        if probe:
            probe_ok, message = _strict_extremum_ok(store, probe)
            if not probe_ok:
                print(f"FAIL tie     {tag}  ({message})")
                ok = False
                continue
            extra = f"  {message}"

        print(f"OK  {tag}  -> {nrows} row(s){extra}")

    print("=" * 60)
    print("ALL GREEN" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline validity gate for a generated few-shot bank.")
    parser.add_argument("--bank", required=True, type=Path, help="Path to the generated_fewshot_bank.yml")
    parser.add_argument("--corpus", required=True, type=Path, help="Path to the corpus.yml carrying the ontology")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Path to the instance-data Turtle; omit for TBox-only structural mode (D-04)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_bank(args.bank, args.corpus, args.data)


if __name__ == "__main__":
    sys.exit(main())
