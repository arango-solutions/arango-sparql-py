"""Query-first synthetic few-shot bank generator (Phase 07.5).

Thin eval-side shim (Stage 2, Plan 06): the pure, ontology-agnostic
**template catalog + slot-filling core** now lives engine-side in
:mod:`arango_query_core.nl.synthbank` (``ShapeTemplate``, ``SHAPE_CATALOG``
with the 9 ``applies``/``build_sparql`` closures, ``RDFS_LABEL_IRI``,
``RELATIONAL_SHAPES``) so Cypher inherits it and it transfers to real
new-ontology onboarding. This module keeps only the parts that CANNOT
promote (Phase 07.5 OQ-2 boundary, ``promote-template-core-only``):

* **data-binding** -- sampling real slot fillers off the live instance
  store, the strict-extremum probe, the execution-non-empty filter -- all
  ``pyoxigraph``-backed (a test-only dep that MUST NOT enter the engine,
  CLAUDE.md hard rule 5 / D-08); every ``pyoxigraph``-touching import stays
  function-local (never module top level);
* **paraphrase** (``paraphrase`` + its offline ``slot_preserving``
  faithfulness guard) -- a build-time LLM concern that imports
  ``arango_sparql``'s own OpenAI-compatible client and so cannot live in the
  language-agnostic engine either;
* the ``generate_bank``/``generate_bank_with_report`` orchestration that
  drives the promoted catalog against a concrete ontology + instance store.

The onboarding caller supplies each promoted shape a pre-bound ``binding``
dict and calls ``shape.build_sparql(binding)``; here that binding is
produced by the per-shape ``_candidates_*`` data-binders below.

See :mod:`arango_query_core.nl.synthbank`'s module docstring for the full
promoted-core contract; the historical Wave-0/1/2 + Plan-05 deviation-fix
notes for the data-binding + paraphrase halves are preserved inline with
their functions below.

Name-anchoring discipline (spike carry-forward #1, MUST): every entity
slot is resolved via the well-known, dataset-independent ``rdfs:label``
(engine ``RDFS_LABEL_IRI``) -- never a per-schema term -- so every emitted
triple references only the ontology's OWN declared vocabulary IRIs plus
``rdfs:label``, satisfying ``verify_generated_bank.py``'s name-anchoring
guard mechanically.
"""

from __future__ import annotations

import os
import random
import re
from collections.abc import Callable
from typing import Any

from arango_query_core.nl.synthbank import (
    RDFS_LABEL_IRI,
    RELATIONAL_SHAPES,
    SHAPE_CATALOG,
    ShapeTemplate,
)

from tests.nl2sparql.eval.grounding_index_builder import (
    PredicateSignals,
    build_predicate_index,
    build_predicate_signals,
)

# Bounded, deterministic sampling caps (RESEARCH "Data-binding +
# execution-filter", Q7 -- reproducible regeneration, bounded build cost).
_MAX_FILLERS_PER_PREDICATE = 2
_MAX_TWO_HOP_PARTNERS = 2

# Name -> ShapeTemplate over the engine-promoted catalog. The per-shape
# ``_candidates_*`` data-binders below reference this (at CALL time) to
# render each shape's own ``question_template`` without duplicating text.
_SHAPES_BY_NAME: dict[str, ShapeTemplate] = {t.name: t for t in SHAPE_CATALOG}


# --------------------------------------------------------------------------
# Small, dependency-free IRI/literal parse helpers for the data-binding side
# (no pyoxigraph -- module-level safe). The engine-side render helper
# ``_lit`` promoted with the catalog; these parse pyoxigraph N-Triples
# lexical output and so stay eval-side with the store code that produces it.
# --------------------------------------------------------------------------


def _parse_numeric(raw: str) -> float:
    """Parse a pyoxigraph N-Triples-lexical numeric literal to ``float``.

    Mirrors ``verify_generated_bank.py::_strict_extremum_ok``'s inline
    parse (split off the ``^^<datatype>`` envelope, strip quotes)."""
    return float(raw.split("^^")[0].strip('"'))


def _clean_literal(raw: str | None) -> str:
    """Normalize a pyoxigraph literal string to plain text (CR-02 style:
    split off ``^^<datatype>``/``@lang`` envelopes BEFORE stripping quotes)."""
    return (raw or "").split('"^^')[0].strip('"').split('"@')[0]


def _strip_iri(term: str | None) -> str:
    """Strip pyoxigraph's ``<...>`` N-Triples envelope from a term."""
    if not term:
        return ""
    return term[1:-1] if term.startswith("<") and term.endswith(">") else term


def _local_name(term: str | None) -> str:
    """IRI (or ``<...>``-wrapped IRI) -> its trailing local name."""
    iri = _strip_iri(term)
    if not iri:
        return ""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _predicates_of(index: Any) -> list[Any]:
    """The flat ``list[GroundedPredicate]`` backing *index* (same private-
    field access already established by ``test_grounding_index_builder.py``
    -- ``PredicateIndex`` has no public iterator)."""
    return list(getattr(index, "_predicates", []))


def _sorted_predicates(index: Any) -> list[Any]:
    """Deterministic (IRI-sorted) predicate list -- generation order must
    not depend on the store's own (unordered) query-result iteration."""
    return sorted(_predicates_of(index), key=lambda p: p.iri)


def _build_class_iri_map(ontology_ttl: str) -> dict[str, str]:
    """Local class name -> full IRI, mechanically derived from the
    ontology's own ``owl:Class`` declarations (function-local pyoxigraph
    import, D-08). ``GroundedPredicate.domain``/``.range`` are LOCAL NAMES
    (see ``build_predicate_index``); this is the missing link back to a
    real class IRI a ``build_sparql`` closure can anchor a triple pattern
    on -- derived structurally, never a hand-picked prefix (mirrors
    ``verify_generated_bank.py::_schema_namespaces``'s own discipline)."""
    from tests.helpers.oxi import load_store_from_string, oxi_query

    store = load_store_from_string(ontology_ttl)
    query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT DISTINCT ?c WHERE { ?c a owl:Class }
    """
    mapping: dict[str, str] = {}
    for row in oxi_query(store, query).rows or []:
        iri = _strip_iri(row.get("c"))
        if iri:
            mapping[_local_name(iri)] = iri
    return mapping


# --------------------------------------------------------------------------
# Data-binding helpers (function-local pyoxigraph, D-08).
# --------------------------------------------------------------------------

# Plan 05 mid-plan deviation fix (Change D): a handful of lookup/
# value_object subject entities are themselves bare monetary/numeric
# VALUES (e.g. a money-value node whose own rdfs:label IS "0,38 EUR")
# rather than a real-world named entity -- the live-LLM regen diagnosis
# (mechanism 3) found these produce genuinely degenerate questions ("what
# is the amount of 0,38 EUR?", i.e. "what is the amount of <the amount
# itself>?") with no faithful natural paraphrase. ``_is_degenerate_value_label``
# below excludes them at generation time; matched narrowly (a pure amount
# [+ unit/currency-code/-symbol] token or two) so a genuine name (e.g. a
# person's name, a product code) never matches.
_CURRENCY_SYMBOLS = frozenset({"$", "€", "£", "¥"})
_NUMERIC_VALUE_TOKEN_RE = re.compile(r"^[$€£¥]?-?\d+(?:[.,]\d+)*$")


def _is_degenerate_value_label(label: str) -> bool:
    """True when *label* is itself a bare numeric/monetary VALUE (e.g.
    ``"0,38 EUR"``, ``"€0.38"``) rather than a real-world named
    entity -- see the module comment above this function for the
    rationale and its own paired unit tests.

    Deliberately conservative: a bare digit-only single token (e.g.
    ``"42"``) is NOT flagged -- with no currency-symbol prefix and no
    unit suffix it could be a legitimate entity code, so this only fires
    when an explicit currency signal (a leading symbol OR a trailing
    currency-code/symbol/percent unit) is also present."""
    tokens = label.strip().split()
    if not tokens or len(tokens) > 2:
        return False
    first = tokens[0]
    if not _NUMERIC_VALUE_TOKEN_RE.match(first):
        return False
    if len(tokens) == 2:
        unit = tokens[1]
        if unit in _CURRENCY_SYMBOLS or unit == "%":
            return True
        return unit.isalpha() and unit.isupper() and 2 <= len(unit) <= 4
    # Single token: only degenerate with an explicit leading currency symbol.
    return first[0] in _CURRENCY_SYMBOLS


def _sample_labels(
    store: Any,
    class_iri: str,
    extra_pattern: str,
    cap: int,
    rng: random.Random,
    *,
    exclude: Callable[[str], bool] | None = None,
) -> list[str]:
    """Up to *cap* distinct ``rdfs:label`` values for ``?x`` matching
    *extra_pattern* (a SPARQL graph pattern referencing ``?x``) -- sorted
    (removing store iteration-order nondeterminism), then seeded-shuffled
    (Q7 reproducibility), THEN optionally filtered by *exclude* (Change D
    -- e.g. :func:`_is_degenerate_value_label`) before capping. Filtering
    AFTER the shuffle (not before) is deliberate: every predicate in a
    shape's generation loop shares the same per-shape ``rng``, and
    filtering-then-shuffling would change the shuffle's input length for
    THIS predicate and silently desync every subsequent predicate's
    shuffle draws -- shuffling first keeps every other predicate's
    sampling byte-identical to the pre-Change-D sequence.

    *class_iri*, when non-empty, additionally constrains ``?x a
    <class_iri>``. Left empty (Rule-1 fix, verified against the real CK25
    data) for a predicate's own SUBJECT side -- several TBox-declared
    domains (``pv:Product``, ``pv:Agent``) are abstract superclasses with
    ZERO direct instances, so requiring the exact declared domain there
    would silently zero out an otherwise-viable, high-value predicate
    (07.4-02's documented finding, re-encountered at generation time).
    Still passed for a RANGE-side anchor (category_filter/two_hop), where
    disambiguating the label match to the correct class remains load-
    bearing."""
    from tests.helpers.oxi import oxi_query

    type_clause = f"?x a <{class_iri}> ." if class_iri else ""
    query = f"""
    SELECT DISTINCT ?label WHERE {{
      {type_clause}
      ?x <{RDFS_LABEL_IRI}> ?label .
      {extra_pattern}
    }}
    """
    rows = oxi_query(store, query).rows or []
    labels = sorted({_clean_literal(r.get("label")) for r in rows if r.get("label")})
    # Shuffle the FULL (unfiltered) list FIRST, then filter -- NOT the
    # other way around. Every predicate in a shape's generation loop
    # shares the SAME per-shape ``rng`` instance (Q7 reproducibility), and
    # ``rng.shuffle``'s draw count depends on the input list's length;
    # filtering before shuffling would change that length for THIS
    # predicate and silently desync every subsequent predicate's shuffle
    # draws from the pre-Change-D sequence (unrelated examples would
    # change too). Shuffling first keeps every OTHER predicate's sampling
    # byte-identical -- only this predicate's own final selection changes.
    rng.shuffle(labels)
    if exclude is not None:
        labels = [label for label in labels if not exclude(label)]
    return labels[:cap]


def _strict_extremum_ok(store: Any, probe: str) -> tuple[bool, str]:
    """Run *probe* (drop-``LIMIT``/``ORDER BY DESC``/top-2 SPARQL) and
    require the extremum be STRICTLY unique (rank1 > rank2) so
    ``LIMIT 1``/``OFFSET 1`` is deterministic (RESEARCH Pitfall 2, the
    ``weight_g``=20.0 saturation lesson). Returns ``(ok, message)``."""
    from tests.helpers.oxi import oxi_query

    result = oxi_query(store, probe)
    values = [list(row.values())[0] for row in (result.rows or [])]
    parsed = [_parse_numeric(v) for v in values]
    if len(parsed) < 2:
        return True, f"probe: only {len(parsed)} value(s) -- trivially unique"
    if parsed[0] <= parsed[1]:
        return False, f"rank1={parsed[0]} <= rank2={parsed[1]}"
    return True, f"probe unique: rank1={parsed[0]} > rank2={parsed[1]}"


def _execution_nonempty(store: Any, query: str) -> bool:
    """REQ-2's execution non-empty filter. A single-row single-column
    result is additionally treated as empty when its value is the
    numeric literal ``0`` -- the "meaningful count" case (RESEARCH
    "Data-binding + execution-filter"): a ``COUNT`` aggregate always
    returns exactly one row even when nothing matched."""
    from tests.helpers.oxi import oxi_query

    result = oxi_query(store, query)
    if result.kind == "ask":
        return bool(result.boolean)
    rows = result.rows or []
    if not rows:
        return False
    if len(rows) == 1 and len(rows[0]) == 1:
        (value,) = rows[0].values()
        try:
            return _parse_numeric(value) != 0
        except ValueError:
            return True
    return True


# --------------------------------------------------------------------------
# Per-shape candidate builders: (predicate, index, class_iri_map, store,
# rng) -> list[(binding, question, probe_or_None)]. Every builder shares
# the same signature for uniform dispatch via ``_CANDIDATE_BUILDERS``, even
# when a given shape does not need every argument. Each renders the paired
# engine-promoted shape's ``question_template`` + emits the pre-bound
# ``binding`` its promoted ``build_sparql`` consumes.
# --------------------------------------------------------------------------


def _candidates_lookup(pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random):
    # No domain-class anchor for the label sample (Rule-1 fix, see
    # engine ``_build_lookup_sparql``/``_sample_labels`` docstrings) -- the
    # predicate's own presence is the real, precise constraint. Change D:
    # exclude a subject whose OWN label is a bare monetary/numeric value
    # -- "what is the amount/currency of <the amount itself>?" is a
    # degenerate question with no faithful natural paraphrase.
    labels = _sample_labels(
        store,
        "",
        f"?x <{pred.iri}> ?v .",
        _MAX_FILLERS_PER_PREDICATE,
        rng,
        exclude=_is_degenerate_value_label,
    )
    template = _SHAPES_BY_NAME["lookup"].question_template
    out = []
    for label in labels:
        binding = {"predicate_iri": pred.iri, "filler_label": label}
        question = template.format(predicate=pred.label, entity=label)
        out.append((binding, question, None))
    return out


def _candidates_value_object(
    pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random
):
    hop_candidates = sorted(
        (p for p in _predicates_of(index) if p.domain == pred.range and p.kind == "datatype"),
        key=lambda p: p.iri,
    )
    if not hop_candidates:
        return []
    hop_pred = hop_candidates[0]
    pattern = f"?x <{pred.iri}> ?mid . ?mid <{hop_pred.iri}> ?v ."
    # Change D (same rationale as ``_candidates_lookup``): exclude a
    # subject whose own label is a bare monetary/numeric value.
    labels = _sample_labels(
        store, "", pattern, _MAX_FILLERS_PER_PREDICATE, rng, exclude=_is_degenerate_value_label
    )
    template = _SHAPES_BY_NAME["value_object"].question_template
    out = []
    for label in labels:
        binding = {
            "predicate_iri": pred.iri,
            "hop_predicate_iri": hop_pred.iri,
            "filler_label": label,
        }
        question = template.format(predicate=pred.label, hop_predicate=hop_pred.label, entity=label)
        out.append((binding, question, None))
    return out


def _relational_anchor(pred: Any, class_iri_map: dict[str, str]) -> tuple[str, str]:
    return class_iri_map.get(pred.range, ""), class_iri_map.get(pred.domain, "")


def _candidates_category_filter(
    pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random
):
    range_iri, domain_iri = _relational_anchor(pred, class_iri_map)
    if not range_iri:
        return []
    # RANGE side still type-anchored (disambiguates the label); DOMAIN
    # side deliberately unconstrained in the sampling pattern too
    # (Rule-1 fix -- mirrors engine ``_build_category_filter_sparql``).
    pattern = f"?d <{pred.iri}> ?x ."
    labels = _sample_labels(store, range_iri, pattern, _MAX_FILLERS_PER_PREDICATE, rng)
    template = _SHAPES_BY_NAME["category_filter"].question_template
    out = []
    for label in labels:
        binding = {
            "range_iri": range_iri,
            "predicate_iri": pred.iri,
            "filler_label": label,
        }
        question = template.format(member_type=pred.domain, category=label)
        out.append((binding, question, None))
    return out


def _candidates_scalar_count(
    pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random
):
    range_iri, domain_iri = _relational_anchor(pred, class_iri_map)
    if not range_iri:
        return []
    pattern = f"?d <{pred.iri}> ?x ."
    labels = _sample_labels(store, range_iri, pattern, _MAX_FILLERS_PER_PREDICATE, rng)
    template = _SHAPES_BY_NAME["scalar_count"].question_template
    out = []
    for label in labels:
        binding = {
            "range_iri": range_iri,
            "predicate_iri": pred.iri,
            "filler_label": label,
        }
        question = template.format(member_type=pred.domain, category=label)
        out.append((binding, question, None))
    return out


def _candidates_grouped_aggregation(
    pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random
):
    from tests.helpers.oxi import oxi_query

    # No domain-class constraint in the group-cardinality probe (Rule-1
    # fix, mirrors engine ``_build_grouped_aggregation_sparql``).
    query = f"""
    SELECT ?g (COUNT(?x) AS ?n) WHERE {{
      ?x <{pred.iri}> ?g .
    }} GROUP BY ?g
    """
    rows = oxi_query(store, query).rows or []
    counts = sorted((int(_parse_numeric(r["n"])) for r in rows if r.get("n")), reverse=True)
    # Need >=2 distinct groups AND a strict gap between the top two counts
    # -- otherwise HAVING(?n > K) is either empty or (K too low) trivially
    # true for every group (the weight_g-saturation lesson, applied to
    # group cardinalities instead of an orderable literal).
    if len(counts) < 2 or counts[0] <= counts[1]:
        return []
    threshold = counts[1]
    template = _SHAPES_BY_NAME["grouped_aggregation"].question_template
    binding = {"predicate_iri": pred.iri, "threshold": threshold}
    question = template.format(group_type=pred.range, threshold=threshold, member_type=pred.domain)
    return [(binding, question, None)]


def _ranking_candidate(pred: Any, class_iri_map: dict[str, str], store: Any, *, offset: int, shape_name: str):
    domain_iri = class_iri_map.get(pred.domain, "")
    if not domain_iri:
        return []
    offset_clause = f" OFFSET {offset}" if offset else ""
    probe = (
        "SELECT ?v WHERE {\n"
        f"  ?result a <{domain_iri}> .\n"
        f"  ?result <{pred.iri}> ?v .\n"
        f"}}\nORDER BY DESC(?v)\nLIMIT 2{offset_clause}"
    )
    ok, _message = _strict_extremum_ok(store, probe)
    if not ok:
        return []
    template = _SHAPES_BY_NAME[shape_name].question_template
    binding = {"domain_iri": domain_iri, "predicate_iri": pred.iri}
    slots = {
        "member_type": pred.domain,
        "order_predicate": pred.label,
        "superlative": "highest",
        "direction": "descending",
    }
    if shape_name == "offset":
        slots["ordinal"] = "second"
    question = template.format(**slots)
    return [(binding, question, probe)]


def _candidates_top_n(pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random):
    return _ranking_candidate(pred, class_iri_map, store, offset=0, shape_name="top_n")


def _candidates_offset(pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random):
    return _ranking_candidate(pred, class_iri_map, store, offset=1, shape_name="offset")


def _candidates_negation(
    pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random
):
    domain_iri = class_iri_map.get(pred.domain, "")
    if not domain_iri:
        return []
    binding = {"domain_iri": domain_iri, "predicate_iri": pred.iri}
    template = _SHAPES_BY_NAME["negation"].question_template
    question = template.format(member_type=pred.domain, predicate=pred.label)
    return [(binding, question, None)]


def _candidates_two_hop(pred: Any, index: Any, class_iri_map: dict[str, str], store: Any, rng: random.Random):
    range_iri, _domain_iri = _relational_anchor(pred, class_iri_map)
    if not range_iri:
        return []
    partners = sorted(
        (
            p
            for p in _predicates_of(index)
            if p.domain == pred.domain and p.iri != pred.iri and p.shape in RELATIONAL_SHAPES
        ),
        key=lambda p: p.iri,
    )
    if not partners:
        return []
    rng.shuffle(partners)
    template = _SHAPES_BY_NAME["two_hop"].question_template
    out = []
    for hop_pred in partners[:_MAX_TWO_HOP_PARTNERS]:
        # No domain-class constraint on the shared subject ?d (Rule-1 fix):
        # the co-occurrence of BOTH predicates is itself the constraint.
        pattern = f"?d <{pred.iri}> ?x . ?d <{hop_pred.iri}> ?v ."
        labels = _sample_labels(store, range_iri, pattern, 1, rng)
        for label in labels:
            binding = {
                "range_iri": range_iri,
                "predicate_iri": pred.iri,
                "hop_predicate_iri": hop_pred.iri,
                "filler_label": label,
            }
            question = template.format(
                far_type=hop_pred.range,
                entity=label,
                near_predicate=pred.label,
                far_predicate=hop_pred.label,
                # ``member_type`` is the shared domain of BOTH predicates
                # (the intermediate ?x's class) -- ``partners`` above is
                # already filtered to ``other.domain == pred.domain``, so
                # ``pred.domain`` == ``hop_pred.domain`` always holds here.
                member_type=pred.domain,
            )
            out.append((binding, question, None))
    return out


_CANDIDATE_BUILDERS: dict[str, Callable[..., list[tuple[dict[str, Any], str, str | None]]]] = {
    "lookup": _candidates_lookup,
    "value_object": _candidates_value_object,
    "category_filter": _candidates_category_filter,
    "scalar_count": _candidates_scalar_count,
    "grouped_aggregation": _candidates_grouped_aggregation,
    "top_n": _candidates_top_n,
    "offset": _candidates_offset,
    "negation": _candidates_negation,
    "two_hop": _candidates_two_hop,
}


# --------------------------------------------------------------------------
# Paraphrase (D-03, Plan 03/Wave 2): K guard-passing natural paraphrases
# per example via the same human-held-key OpenAICompatibleClient provider,
# gated by the PRIMARY offline/deterministic slot-preservation guard.
# Stays eval-side (Plan 06): imports arango_sparql's own LLM client, so it
# cannot live in the language-agnostic engine; the guard travels with it.
# --------------------------------------------------------------------------

# Ranking shapes (top_n/offset) are ALWAYS rendered by this generator's own
# ``_ranking_candidate`` in descending/"highest" order -- there is no
# per-example "ascending" variant to preserve, so the guard below checks a
# FIXED canonical direction, not a value read out of ``binding`` (Q7-style
# generator invariant, not a per-example fact).
_SUPERLATIVE_POSITIVE = frozenset({"most", "highest", "largest", "greatest", "top"})
_SUPERLATIVE_NEGATIVE = frozenset(
    {"least", "lowest", "smallest", "cheapest", "fewest", "minimum", "bottom", "worst"}
)

# ``binding`` keys that carry a literal filler value a faithful paraphrase
# MUST preserve verbatim (case-insensitive) -- the template + binding pair
# is D-03's ground truth, per the plan's own scope ("every literal filler
# in binding"). Not every shape's binding carries one of these (e.g.
# top_n/offset/negation bind only IRIs, no user-facing literal) -- absent
# keys are silently skipped, never treated as a violation.
_FILLER_BINDING_KEYS = ("filler_label", "threshold")


def _normalize_filler_text(text: str) -> str:
    """Conservatively normalize *text* for the filler-substring
    faithfulness check (Plan 05 mid-plan deviation fix, Change C):
    unify a decimal comma (a comma directly between two digits, e.g.
    ``"0,38"`` -> ``"0.38"``) to a period, and collapse any run of
    whitespace to a single space.

    Deliberately narrow -- never strips digits, currency codes/symbols,
    or any other token, so the numeric value + unit must still be
    present in *some* normalized form: a paraphrase that CHANGES the
    value (e.g. ``"0,38"`` -> ``"0,39"``) or the currency (e.g. ``"EUR"``
    -> ``"USD"``) still fails the substring check after this
    normalization -- faithfulness holds (see the paired unit tests)."""
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", text)
    return re.sub(r"\s+", " ", normalized).strip()


def slot_preserving(paraphrase: str, template: ShapeTemplate, binding: dict[str, Any]) -> bool:
    """PRIMARY faithfulness guard (D-03) -- pure, offline, deterministic,
    and NEVER calls an LLM (mechanical text checks only, no client/generate
    call anywhere in this function).

    A *paraphrase* is faithful to its paired *template* + *binding* iff:

    1. Every literal filler value bound into the query (``binding``'s
       ``filler_label``/``threshold``, when present) still appears in
       *paraphrase*, case-insensitively -- a paraphrase that drops the
       category/department/country/threshold filler is REJECTED. The
       comparison is normalized for a decimal-comma/period and
       whitespace-run mismatch ONLY (Change C, :func:`_normalize_filler_text`)
       -- a paraphrase that reformats ``"0,38 EUR"`` to ``"0.38 EUR"`` still
       passes, but one that CHANGES the value or currency (e.g. ``"0,39
       EUR"``, ``"0.38 USD"``) still fails, since no digit/currency-code is
       ever stripped.
    2. For a shape carrying a non-empty ``intent_lexicon``, *paraphrase*
       contains at least one of that shape's intent tokens (e.g.
       scalar_count needs "how many"/"number of"/"count"; negation needs
       "without"/"no"/"lacking"/...) -- dropping the shape's own intent
       entirely is REJECTED.
    3. For the two ranking shapes (``top_n``/``offset`` -- both always
       rendered in descending/"highest" order by this generator), a
       paraphrase using an OPPOSITE-direction superlative (e.g. "cheapest"/
       "lowest" on a "most expensive"/"highest" question) is REJECTED even
       though it may otherwise look fluent -- this is the shape-intent
       FLIP the guard exists to catch (D-03's own worked example).

    The paired template is ground truth (D-03); this is the primary guard.
    An LLM-judge sample check is a *secondary* audit, run separately
    (human-run, Plan 05) -- never folded into this function.
    """
    text = _normalize_filler_text(paraphrase.lower())

    for key in _FILLER_BINDING_KEYS:
        value = binding.get(key)
        if value is None:
            continue
        filler = _normalize_filler_text(str(value).strip().lower())
        if filler not in text:
            return False

    if template.name in ("top_n", "offset"):
        if any(token in text for token in _SUPERLATIVE_NEGATIVE):
            return False
        if not any(token in text for token in _SUPERLATIVE_POSITIVE):
            return False
        return True

    lexicon = template.intent_lexicon
    if not lexicon:
        return True
    return any(token in text for token in lexicon)


def paraphrase(
    question: str,
    template: ShapeTemplate,
    binding: dict[str, Any],
    *,
    k: int = 3,
    client: Any = None,
) -> list[str]:
    """Up to *k* guard-passing natural paraphrases of *question* for the
    paired *template* (+ *binding*) -- D-03.

    Build-time LLM dependency (D-03): "auto-onboard any ontology" means
    auto GIVEN LLM access at build time, not hands-free -- this function's
    default path constructs an ``OpenAICompatibleClient`` exactly as
    ``runner._client_for`` does (``provider="openai"``, model default
    ``"gpt-4o-mini"``; function-local import, mirroring this module's own
    pyoxigraph-import discipline so a caller with no ``requests``/key
    configured can still import this module and use ``slot_preserving``
    offline) and reads the human-held ``NL2SPARQL_API_KEY``.

    Offline tests / offline bank regeneration inject a scripted double (no
    key, no network) via *client* -- any object satisfying the
    ``LLMClient`` duck-typing protocol (``.generate(messages) ->
    LLMResponse``, e.g. ``ScriptedLLMClient``).

    When *client* is ``None`` and no ``NL2SPARQL_API_KEY`` is configured,
    this degrades to an empty list -- callers keep the single templated
    *question* with no paraphrases (an honest, documented degrade; NEVER a
    crash, and NEVER a silent live call made without a key).

    Candidates failing :func:`slot_preserving` are rejected and another is
    requested, bounded by ``k * 5`` total attempts (a paraphrase that
    cannot be made faithful within the retry budget is simply dropped --
    the example still ships with fewer than *k* paraphrases, or none).

    Plan 05 mid-plan deviation fix (Change A): two credentialed regen runs
    (temp 0.1 then 0.9) proved the OLD ``k * 3`` budget + unprompted
    request left a real LLM settling into near-repeats that the exact-
    lowercased ``seen`` dedup then silently discarded, capping several
    trivial-guard shapes (empty ``intent_lexicon`` -- category_filter/
    lookup/two_hop/value_object) at 2 accepted instead of 3. Every attempt
    from the 2nd accepted candidate on now appends an explicit
    "already-produced paraphrases" note (echoing back every candidate
    accepted so far) instructing the model to produce a genuinely NEW,
    DISTINCT paraphrase -- and the system prompt now explicitly forbids
    reformatting any number/currency/unit or shortening any named entity,
    to reduce the literal-reformatting faithfulness failures the same
    regen diagnosed (mechanism 3; the residual cases are caught by
    :func:`slot_preserving`'s own normalized filler check, never silently
    let through). The DEFAULT client construction path (``client is
    None``) also raises its temperature from the inherited 0.1 to 0.7 --
    the shipped "auto-onboard any ontology" product path needs paraphrase
    VARIETY by default, not near-deterministic near-repeats; an injected
    *client* (offline tests / offline regeneration) is unaffected.
    """
    if client is None:
        if not os.getenv("NL2SPARQL_API_KEY"):
            return []
        from arango_sparql.nl2sparql.client import OpenAICompatibleClient

        client = OpenAICompatibleClient(provider="openai", model="gpt-4o-mini", temperature=0.7)

    accepted: list[str] = []
    seen: set[str] = {question.strip().lower()}
    max_attempts = max(k * 5, 1)
    system_message = {
        "role": "system",
        "content": (
            "Paraphrase the given natural-language question in a single "
            "sentence. Keep every named entity, number, currency amount, "
            "and unit EXACTLY as written in the question -- do NOT "
            "reformat a number (e.g. do not change a decimal separator or "
            "add/drop digits), do NOT translate, abbreviate, or drop any "
            "currency, and do NOT shorten or rephrase any named entity. "
            "Preserve the question's exact intent (do not drop or flip any "
            "filter, count, ordering, or negation). Return ONLY the "
            "paraphrased question text, no extra commentary."
        ),
    }
    for _attempt in range(max_attempts):
        if len(accepted) >= k:
            break
        user_content = question
        if accepted:
            # Force novelty (Change A): tell the model what has already
            # been produced and ask for a genuinely NEW, distinct
            # paraphrase -- the diagnosed failure mode is the model
            # settling into near-repeats that the `seen` dedup below then
            # silently discards without ever reaching k accepted.
            already = "\n".join(f"- {p}" for p in accepted)
            user_content = (
                f"{question}\n\n"
                "Already-produced paraphrases (produce a NEW, DISTINCT "
                "paraphrase -- not a near-repeat of any of these):\n"
                f"{already}"
            )
        messages = [system_message, {"role": "user", "content": user_content}]
        response = client.generate(messages)
        candidate = (response.content or "").strip()
        normalized = candidate.lower()
        if not candidate or normalized in seen:
            continue
        seen.add(normalized)
        if slot_preserving(candidate, template, binding):
            accepted.append(candidate)
    return accepted


def generate_bank_with_report(
    ontology_ttl: str,
    data_ttl: str | None = None,
    *,
    k_paraphrases: int = 3,
    seed: int = 0,
    client: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Full pipeline: build the predicate index + Wave 0 signals, enumerate
    real slot fillers per (shape, applicable-predicate) via a seeded
    bounded sampler, instantiate + execution-filter each candidate (REQ-2),
    and apply the strict-extremum gate to ranking shapes -- returning
    ``(bank, report)`` where ``bank`` is ``{"version": 1, "examples": [...]}``
    (each example carries ``question``/``query`` (+ ``shape``, + ``probe``
    for ranking shapes)) and ``report`` is the first-class per-shape yield
    report (kept/dropped counts + drop reasons, D-02 -- a hard shape
    yielding ~0 is a measured, logged finding, never a silent gap,
    RESEARCH Pitfall 6). The compositional shapes themselves come from the
    engine-promoted ``SHAPE_CATALOG`` (their ``applies`` gates + slot-
    filling ``build_sparql`` renderers); this function owns only the
    ontology-specific data-binding that feeds them.

    ``k_paraphrases`` is the K passed to :func:`paraphrase` for each kept
    example (D-03); ``client`` is forwarded to :func:`paraphrase` unchanged
    (``None`` -> the human-held-key ``OpenAICompatibleClient`` default, or
    an honest empty-paraphrases degrade when no key is configured; a
    scripted double for offline tests / offline bank regeneration). An
    example whose paraphrases list ends up empty still ships (the single
    templated ``question`` is always present) -- ``paraphrases`` is only
    added to an example when non-empty. ``seed`` seeds a per-shape
    deterministic ``random.Random`` substream (Q7 -- regeneration with the
    same seed AND the same deterministic ``client`` is byte-stable).

    When *data_ttl* is omitted (TBox-only, e.g. QALD, D-04), every Stage-1
    shape here is data-bound (label sampling, execution-filter,
    strict-extremum) and cannot produce a candidate -- this degrades to an
    honest empty bank with every shape's drop reason recorded, never a
    crash.
    """
    index = build_predicate_index(ontology_ttl)
    signals = build_predicate_signals(ontology_ttl, data_ttl)
    predicates = _sorted_predicates(index)

    report: dict[str, Any] = {t.name: {"kept": 0, "dropped": 0, "reasons": []} for t in SHAPE_CATALOG}

    if data_ttl is None:
        for t in SHAPE_CATALOG:
            report[t.name]["reasons"].append(
                "no instance data supplied (TBox-only) -- every Stage-1 shape here is data-bound"
            )
        return {"version": 1, "examples": []}, report

    from tests.helpers.oxi import load_store_from_string

    store = load_store_from_string(data_ttl)
    class_iri_map = _build_class_iri_map(ontology_ttl)

    examples: list[dict[str, Any]] = []

    for shape in SHAPE_CATALOG:
        rng = random.Random(f"{seed}:{shape.name}")
        shape_hit = False
        for pred in predicates:
            if not shape.applies(pred, index, signals):
                continue
            shape_hit = True
            builder = _CANDIDATE_BUILDERS[shape.name]
            candidates = builder(pred, index, class_iri_map, store, rng)
            if not candidates:
                report[shape.name]["dropped"] += 1
                report[shape.name]["reasons"].append(
                    f"{pred.label} ({pred.iri}): no viable data-bound candidate "
                    "(empty filler pool / saturated-tied orderable / no surviving threshold)"
                )
                continue
            for binding, question, probe in candidates:
                query = shape.build_sparql(binding)
                if not _execution_nonempty(store, query):
                    report[shape.name]["dropped"] += 1
                    report[shape.name]["reasons"].append(
                        f"{pred.label} ({pred.iri}): candidate executed empty, dropped"
                    )
                    continue
                if probe is not None:
                    ok, message = _strict_extremum_ok(store, probe)
                    if not ok:
                        report[shape.name]["dropped"] += 1
                        report[shape.name]["reasons"].append(
                            f"{pred.label} ({pred.iri}): {message} (saturated/tied orderable, dropped)"
                        )
                        continue
                example: dict[str, Any] = {"question": question, "query": query, "shape": shape.name}
                if probe is not None:
                    example["probe"] = probe
                paraphrases = paraphrase(question, shape, binding, k=k_paraphrases, client=client)
                if paraphrases:
                    example["paraphrases"] = paraphrases
                examples.append(example)
                report[shape.name]["kept"] += 1
        if not shape_hit:
            report[shape.name]["reasons"].append(
                "no predicate in this ontology satisfies this shape's applies() gate"
            )

    examples.sort(key=lambda e: (e["shape"], e["question"]))
    return {"version": 1, "examples": examples}, report


def generate_bank(
    ontology_ttl: str,
    data_ttl: str | None = None,
    *,
    k_paraphrases: int = 3,
    seed: int = 0,
    client: Any = None,
) -> dict[str, Any]:
    """Emit a per-ontology few-shot bank dict from *ontology_ttl*
    (+ optional *data_ttl*) via the engine-promoted ``SHAPE_CATALOG``'s
    compositional templates.

    Thin wrapper over :func:`generate_bank_with_report` that discards the
    per-shape yield report -- see that function for the full pipeline
    description (including ``client``/``k_paraphrases`` -- D-03 paraphrase
    generation) and the report's shape. Callers that need the report
    (e.g. the CK25 bank-generation step, or a unit test asserting every
    catalog shape is accounted for) should call
    :func:`generate_bank_with_report` directly.
    """
    bank, _report = generate_bank_with_report(
        ontology_ttl, data_ttl, k_paraphrases=k_paraphrases, seed=seed, client=client
    )
    return bank
