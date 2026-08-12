"""Fast, no-network unit tests for the execution-answer judge (`_judge_execution`).

These are deliberately NOT under `@pytest.mark.eval` / `RUN_EVAL`: pyoxigraph runs
in-process against tiny inline-Turtle fixtures — no network call, no API key — so
this belongs on the default CI path, mirroring `test_judge.py`'s own stated
rationale for the canonical judge.

The property under test is D-02..D-05 from `07.2-CONTEXT.md`: the execution judge
grades gold vs. candidate SPARQL by running both through pyoxigraph and comparing
ANSWERS (not query structure) — up to variable renaming and IRI<->label
normalization, for both SELECT and ASK forms, with gold-engine-limit vs.
candidate-engine-reject exceptions surfaced as distinct tags rather than a silent
bare fail.
"""

from __future__ import annotations

from types import SimpleNamespace

from tests.helpers.oxi import load_store_from_string, oxi_query
from tests.nl2sparql.eval.runner import _judge, _judge_canonical, _judge_execution

_PREFIX = "PREFIX : <http://ex.org/>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"


def _outcome(sparql: str) -> SimpleNamespace:
    """A stand-in `NlPipeline.run()` outcome — only `.aql`/`.sparql` are read."""
    return SimpleNamespace(aql="FOR x IN y RETURN x", sparql=sparql)


def test_ask_branch_compares_booleans() -> None:
    """ASK never touches `.variables` (pyoxigraph's `QueryBoolean` has none) —
    the judge must compare booleans, both at the `oxi_query` layer directly and
    through the full `_judge_execution` entry point."""
    data = _PREFIX + ":alice a :Person .\n"
    store = load_store_from_string(data)

    ask_true = oxi_query(store, _PREFIX + "ASK { ?s a :Person }")
    ask_false = oxi_query(store, _PREFIX + "ASK { ?s a :Robot }")
    assert ask_true.kind == "ask"
    assert ask_true.boolean is True
    assert ask_false.kind == "ask"
    assert ask_false.boolean is False

    gold = _PREFIX + "ASK { ?s a :Person }"
    passed, note = _judge_execution(gold, _outcome(_PREFIX + "ASK { ?s a :Person }"), data)
    assert passed is True
    assert note is None

    passed, note = _judge_execution(gold, _outcome(_PREFIX + "ASK { ?s a :Robot }"), data)
    assert passed is False


def test_var_rename_insensitive_row_match() -> None:
    """A candidate that renames every projected variable must still match the
    gold's answer set. One fixture row carries the SAME string value bound to
    two different projected variables (a multi-value row) to exercise the
    duplicate-safe sorted-tuple row key (Pattern 4) rather than a frozenset,
    which would silently collapse the duplicate."""
    data = _PREFIX + ':alice :val "x" ; :val2 "x" .\n' + ':bob :val "y" ; :val2 "z" .\n'
    gold = _PREFIX + "SELECT ?a ?b WHERE { ?s :val ?a ; :val2 ?b }"
    candidate = _PREFIX + "SELECT ?p ?q WHERE { ?s :val ?p ; :val2 ?q }"

    passed, note = _judge_execution(gold, _outcome(candidate), data)
    assert passed is True
    assert note is None


def test_iri_label_normalization() -> None:
    """A gold projecting an entity IRI and a candidate projecting that same
    entity's `rdfs:label` must be treated as an equivalent answer (D-03)."""
    data = _PREFIX + ':p1 a :Person ; rdfs:label "Alice" .\n'
    gold = _PREFIX + "SELECT ?s WHERE { ?s a :Person }"
    candidate = _PREFIX + "SELECT ?label WHERE { ?s a :Person ; rdfs:label ?label }"

    passed, note = _judge_execution(gold, _outcome(candidate), data)
    assert passed is True
    assert note is None


def test_xsd_int_gold_normalization() -> None:
    """A gold using `xsd:int(...)` (a derived XSD type with no implicit SPARQL
    constructor -- pyoxigraph rejects it outright) must execute without raising
    after the judge's `xsd:int(` -> `xsd:integer(` pre-pass (Pattern 3), and
    must not surface as a `gold_engine_limitation`."""
    data = _PREFIX + ':item :qty "72" .\n'
    xsd_prefix = "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
    gold = _PREFIX + xsd_prefix + "SELECT (xsd:int(?q) AS ?n) WHERE { :item :qty ?q }"
    candidate = _PREFIX + xsd_prefix + "SELECT (xsd:integer(?q) AS ?n) WHERE { :item :qty ?q }"

    passed, note = _judge_execution(gold, _outcome(candidate), data)
    assert passed is True
    assert note is None


def test_engine_exceptions_are_tagged_not_silent() -> None:
    """A gold-side pyoxigraph failure and a candidate-side pyoxigraph failure
    must each surface as a distinct, non-None `judge_note` string -- never a
    silent bare `False` that looks like an ordinary wrong-answer fail (D-05)."""
    data = _PREFIX + ":alice a :Person .\n"
    good = _PREFIX + "SELECT ?s WHERE { ?s a :Person }"
    # Missing closing brace -- pyoxigraph raises SyntaxError on this text.
    unparseable = _PREFIX + "SELECT ?s WHERE { ?s a :Person "

    passed, note = _judge_execution(unparseable, _outcome(good), data)
    assert passed is False
    assert note is not None
    assert note.startswith("gold_engine_limitation")

    passed, note = _judge_execution(good, _outcome(unparseable), data)
    assert passed is False
    assert note is not None
    assert note.startswith("candidate_engine_rejected")


def test_execution_judge_fires_not_silently_canonical() -> None:
    """Proves the DISPATCHER (not just `_judge_execution` in isolation) actually
    routes to the execution judge on a corpus-level `data_ttl` (BLOCKER fix).

    The gold projects an entity IRI (`?person`); the candidate projects a
    variable-renamed, label-projecting query for the SAME entity (`?p` bound to
    `rdfs:label`). This is answer-equivalent (execution judge PASSES) but
    structurally different (canonical judge REJECTS) -- exactly the CK25
    failure mode this phase exists to fix. `case` carries NO per-case `data:`
    field, mirroring CK25's actual corpus shape; only the corpus-level
    `data_ttl` passed to the 4-arg `_judge` may make this fire.
    """
    data = _PREFIX + ':emp1 a :Employee ; rdfs:label "Karen Brant" .\n'
    gold = _PREFIX + "SELECT ?person WHERE { ?person a :Employee }"
    candidate = _PREFIX + "SELECT ?p WHERE { ?e a :Employee ; rdfs:label ?p }"
    case = {"name": "disc", "expected": gold}  # no `data` key -- mirrors CK25
    outcome = _outcome(candidate)

    passed, note = _judge("execution", case, outcome, data_ttl=data)
    assert passed is True

    # Same pair, canonical judge: genuinely different algebra (IRI projection
    # vs. an extra rdfs:label triple pattern + differently-named projection)
    # -- must NOT pass. If the dispatcher's guard still keyed solely on
    # `case.get("data")` it would fall through to canonical here and the
    # assertion above would have failed instead.
    assert _judge_canonical(gold, outcome) is False


def test_extra_projected_column_still_matches() -> None:
    """Projection tolerance: a candidate that projects the gold answer PLUS an
    extra descriptive column (a superlative that also selects its sort key -- the
    ck25-18/19/24 judge-artifact shape) is the same answer. A candidate that
    returns the WRONG entity in that column must still fail."""
    data = _PREFIX + ":a a :Osc ; :price 1 .\n:b a :Osc ; :price 2 .\n"
    gold = _PREFIX + "SELECT ?r WHERE { ?r a :Osc ; :price ?p } ORDER BY ASC(?p) LIMIT 1"
    # same cheapest entity, but the candidate also projects the price column
    cand = _PREFIX + "SELECT ?r ?p WHERE { ?r a :Osc ; :price ?p } ORDER BY ASC(?p) LIMIT 1"
    passed, note = _judge_execution(gold, _outcome(cand), data)
    assert passed is True
    assert note is None
    # the most-expensive (wrong) entity, also with an extra column, must NOT match
    wrong = _PREFIX + "SELECT ?r ?p WHERE { ?r a :Osc ; :price ?p } ORDER BY DESC(?p) LIMIT 1"
    passed, _ = _judge_execution(gold, _outcome(wrong), data)
    assert passed is False


def test_symmetric_duplicate_rows_match_as_set() -> None:
    """Set relaxation: a self-join emitting each mutual pair in BOTH directions is
    the same answer set as a gold that canonicalizes direction via a `STR(?x) <
    STR(?y)` filter (the ck25-43 judge-artifact shape)."""
    data = _PREFIX + ":a :compat :b .\n:b :compat :a .\n"
    gold = _PREFIX + "SELECT ?x ?y WHERE { ?x :compat ?y . FILTER(STR(?x) < STR(?y)) }"
    cand = _PREFIX + "SELECT ?x ?y WHERE { ?x :compat ?y }"
    passed, note = _judge_execution(gold, _outcome(cand), data)
    assert passed is True
    assert note is None


def test_relaxation_rejects_extra_wrong_rows() -> None:
    """Soundness guard: the set/projection relaxations must NOT pass a candidate
    that returns the gold answers PLUS additional distinct (wrong) rows -- the
    projected/deduped set then differs from gold, so it stays a fail."""
    data = _PREFIX + ":a a :Osc .\n:b a :Osc .\n"
    gold = _PREFIX + "SELECT ?r WHERE { ?r a :Osc } LIMIT 1"  # exactly one entity
    cand = _PREFIX + "SELECT ?r WHERE { ?r a :Osc }"  # both entities -- a superset
    passed, _ = _judge_execution(gold, _outcome(cand), data)
    assert passed is False
