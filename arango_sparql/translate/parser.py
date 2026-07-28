"""Thin wrapper over :mod:`rdflib.plugins.sparql` for SPARQL 1.1 parsing.

The rest of the codebase MUST use this module rather than touching
``rdflib`` directly so that:

1. Parser errors are converted to :class:`~arango_sparql.errors.SparqlParseError`
   with stable error codes for the HTTP layer.
2. The Algebra translation step (``translateQuery``) is always applied,
   so visitors see the optimized algebra rather than the raw parse tree.
3. The original projection-variable declaration order is preserved.
   ``rdflib.algebra.translateQuery`` collapses ``Project.PV`` into a
   set-iteration order that is **non-deterministic** across Python runs
   (set hash randomization). We capture the explicit projection list
   from the parsed query before that information is lost.

See ``.cursor/skills/sparql-to-aql/SKILL.md`` step 1 for the algebra
inspection workflow.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from rdflib import URIRef, Variable
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery

from ..errors import SparqlParseError

# rdflib's SPARQL grammar (``rdflib.plugins.sparql.parser``) is built on
# pyparsing ``ParserElement`` objects that are module-level *singletons*
# (e.g. ``IRIREF.set_parse_action(lambda x: rdflib.URIRef(x[0]))``,
# ``BLANK_NODE_LABEL``, ``INTEGER``, ...) — the same shared grammar
# instances parse every query, in every thread. pyparsing's internal
# parse-in-progress state on those shared objects is not safe for
# concurrent use from multiple threads: two overlapping ``parseQuery``
# calls can interleave and corrupt each other's state, surfacing as a
# spurious ``TypeError`` from one of the grammar's own parse-action
# lambdas (observed here as ``<lambda>() missing 1 required positional
# argument: 'x'`` under concurrent ``/execute`` load — PRD §9.4's
# concurrency report row, ``tests/perf/test_concurrency.py``, is what
# first surfaced this). This service is deployed behind FastAPI's
# threaded request handling, so concurrent requests are the norm, not
# an edge case — this module-level lock serializes the two rdflib calls
# that touch the shared grammar/algebra machinery so concurrent
# ``/execute``/``/sparql``/``/translate`` calls never race.
_PARSE_LOCK = threading.Lock()


@dataclass
class ParsedSparql:
    """Result of :func:`parse_sparql`.

    ``algebra`` is the rdflib Algebra root node the visitor walks.
    ``explicit_projection`` is the declared projection variable list
    *iff* the query used an explicit ``SELECT ?a ?b`` form; ``None``
    when the query used ``SELECT *`` (in which case the visitor falls
    back to its own deterministic variable-binding order).

    ``describe_resources`` is the declared resource list for a
    ``DESCRIBE`` query — either the explicit IRI list (``DESCRIBE
    <a> <b>``) or the variable list (``DESCRIBE ?s ?o WHERE …``).
    The visitor reads this in preference to the algebra's ``PV``
    field because ``translateQuery`` collapses ``PV`` through a set
    iteration (non-deterministic across Python runs courtesy of
    ``PYTHONHASHSEED``). ``None`` for non-DESCRIBE queries and for
    ``DESCRIBE *`` (which rdflib stores as the literal string
    ``"var"`` — an unsupported shape that the visitor will refuse
    cleanly).
    """

    algebra: Any
    explicit_projection: list[Variable] | None = None
    describe_resources: list[Variable | URIRef] | None = None


def parse_sparql(query: str) -> ParsedSparql:
    """Parse *query* and return the rdflib Algebra plus declared projection.

    Raises
    ------
    SparqlParseError
        If ``rdflib`` cannot parse the input string.
    """
    if not isinstance(query, str) or not query.strip():
        raise SparqlParseError("SPARQL query must be a non-empty string")
    try:
        with _PARSE_LOCK:
            parsed = parseQuery(query)
            translated = translateQuery(parsed)
    except Exception as exc:
        raise SparqlParseError(f"failed to parse SPARQL: {exc}") from exc
    explicit = _extract_explicit_projection(parsed)
    describe = _extract_describe_resources(parsed)
    return ParsedSparql(
        algebra=translated.algebra,
        explicit_projection=explicit,
        describe_resources=describe,
    )


def _extract_explicit_projection(parsed: Any) -> list[Variable] | None:
    """Return the declared projection list, or ``None`` for ``SELECT *``.

    rdflib's ``parseQuery`` returns ``(prologue, query)``. For an
    explicit projection (``SELECT ?a ?b``) the query carries a
    ``projection`` key whose value is a list of ``vars`` records — each
    with a ``var`` slot pointing at the actual ``Variable``. ``SELECT *``
    omits the key entirely.
    """
    try:
        _, query = parsed
    except (ValueError, TypeError):
        return None
    if getattr(query, "name", None) != "SelectQuery":
        return None
    projection = query.get("projection")
    if not projection:
        return None
    out: list[Variable] = []
    for entry in projection:
        if not hasattr(entry, "get"):
            continue
        # Plain ``?x`` projection entries set ``var``; aliased
        # projections (``(<expr> AS ?x)``, including aggregates and
        # ``BIND``-shaped projections inside SELECT) set ``evar``.
        # Both produce the same downstream binding semantics — pick
        # whichever the entry carries.
        #
        # Subtlety: rdflib's ``CompValue.get`` returns the *key name*
        # as the default when the key is absent (instead of ``None``),
        # so we must verify the result is actually a ``Variable``
        # before treating it as one.
        var = entry.get("var")
        if not isinstance(var, Variable):
            var = entry.get("evar")
        if isinstance(var, Variable):
            out.append(var)
    return out or None


def _extract_describe_resources(parsed: Any) -> list[Variable | URIRef] | None:
    """Return the declared DESCRIBE resource list in source order.

    Mirrors :func:`_extract_explicit_projection` but for DESCRIBE: the
    pre-translation parsed query carries a ``"var"`` slot on the
    DescribeQuery node that holds either a list of explicit terms
    (``DESCRIBE <a> <b>`` → ``[<a>, <b>]``, ``DESCRIBE ?s ?o`` →
    ``[?s, ?o]``) or the literal string ``"var"`` for the wildcard
    ``DESCRIBE *`` shape (an inert sentinel from rdflib's
    ``CompValue.get`` default-key behaviour).

    Returns ``None`` for non-DESCRIBE queries and for the wildcard
    sentinel; the visitor turns ``None`` for a DESCRIBE into a
    typed error so a wildcard never silently degrades to "describe
    nothing".
    """

    try:
        _, query = parsed
    except (ValueError, TypeError):
        return None
    if getattr(query, "name", None) != "DescribeQuery":
        return None
    raw = query.get("var")
    if not isinstance(raw, list):
        # ``CompValue.get`` returns the key name when the slot is
        # missing — the wildcard ``DESCRIBE *`` case lands here.
        return None
    out: list[Variable | URIRef] = []
    for term in raw:
        if isinstance(term, (Variable, URIRef)):
            out.append(term)
    return out or None
