"""Query-first synthetic few-shot bank generator (Phase 07.5, Stage 1).

Given an ontology's TBox (+ optional instance data), ``generate_bank``
emits a per-ontology ``(question, gold-SPARQL)`` few-shot bank via a
typed catalog of ontology-agnostic compositional SPARQL shapes
(``SHAPE_CATALOG``), instantiated against a ``PredicateIndex``
(``build_predicate_index``) + the Wave 0 ``PredicateSignals``
(``build_predicate_signals``) -- see ``grounding_index_builder.py``.

Packaging boundary (CLAUDE.md hard rule 5): this file MUST live under
``tests/`` and MUST NOT be imported by ``arango_query_core``/``arango_sparql``
proper. Every ``pyoxigraph``-touching import stays function-local (never at
module top level) so those packages never gain a transitive ``pyoxigraph``
import path -- mirroring ``grounding_index_builder.py``'s own discipline
(D-08). This applies equally to every function in this file, including
``generate_bank`` once its data-binding/execution-filter logic lands
(Plan 02 Task 2).

Wave 1 Task 1 (this commit): the 9 ``ShapeTemplate.applies``/
``build_sparql`` closures are fully implemented and schema-agnostic --
each reads ONLY ``GroundedPredicate`` fields (``kind``/``domain``/
``range``/``shape``/``shape_detail``), the Wave 0 ``PredicateSignals``
(``orderable``/``optional_relation``), and its own hand-supplied binding
-- NEVER a hardcoded vocabulary term (verified by re-running the same
closures against a synthetic, non-CK25 ontology in
``test_bank_generator.py``). ``generate_bank`` itself remains a Wave 0
stub (raises ``NotImplementedError``) -- the slot-fill + data-bind +
execution-filter + strict-extremum pipeline that calls these closures
lands in Task 2.

Name-anchoring discipline (spike carry-forward #1, MUST): every entity
slot is resolved via ``rdfs:label`` -- verified against the real CK25
instance data that every subject carrying the vocabulary's own ``pv:name``
also carries an identical-valued ``rdfs:label`` (0 counterexamples), and
``rdfs:label`` covers strictly more subjects. Using ONLY the well-known,
dataset-independent ``rdfs:label`` (never a per-schema term) keeps every
``build_sparql`` closure schema-agnostic per D-02/REQ-5, and every emitted
triple pattern references only the ontology's OWN declared vocabulary
IRIs (classes/predicates) plus ``rdfs:label`` -- never a hardcoded
instance-namespace IRI (CK25's ``prodi:``), satisfying the
``verify_generated_bank.py`` name-anchoring guard mechanically.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tests.nl2sparql.eval.grounding_index_builder import PredicateSignals

# Well-known, dataset-INDEPENDENT RDF vocabulary term -- never a per-schema
# hint (D-02 discipline). Verified against real CK25 instance data (see
# module docstring): every ``pv:name``-carrying subject also carries an
# identical-valued ``rdfs:label``, and ``rdfs:label`` covers strictly more
# subjects -- so this ALONE is a sufficient, schema-agnostic name-anchor
# predicate for every shape below.
RDFS_LABEL_IRI = "http://www.w3.org/2000/01/rdf-schema#label"

# The two ``GroundedPredicate.shape`` values whose RANGE side is a
# real, enumerable, label-anchorable "entity" class (as opposed to
# ``"literal"`` -- a plain datatype value -- or ``"value_object"`` -- an
# intermediate blank-ish node reached only via an extra hop). Mechanical,
# derived from the 07.4 walker's own classification -- never a term-name
# special case.
RELATIONAL_SHAPES = frozenset({"category_instance", "linked_entity"})


@dataclass(frozen=True)
class ShapeTemplate:
    """One compositional SPARQL shape in the generator's typed catalog.

    ``applies`` gates whether a given ``GroundedPredicate`` (+ its home
    ``PredicateIndex``) is a candidate for this shape. ``build_sparql``
    renders the slot-filled, name-anchored SPARQL text for a matched
    binding. Both callables must read ONLY ``GroundedPredicate`` fields
    (``kind``/``domain``/``range``/``shape``/``shape_detail``), the Wave 0
    ``PredicateSignals`` (``orderable``/``optional_relation``), and sampled
    instance data -- NEVER a hardcoded vocabulary term (SPEC schema-agnostic
    constraint / D-02; ``grounding_index_builder.py``'s own docstring
    forbids per-schema hints, and this catalog inherits that rule so the
    same generator runs unmodified on CK25 and QALD, per REQ-5).

    ``semantic_slots`` are the shape's first-class, machine-readable
    faithfulness ground truth (D-03): the named fillers (e.g. ``"category"``,
    ``"order_predicate"``, ``"direction"``) a paraphrase must preserve.
    Making these data -- not text buried in a rendered question -- is what
    makes D-03's primary slot-preservation guard a mechanical set/dict
    comparison rather than a regex over prose.

    ``intent_lexicon`` is the shape's own paraphrase guard vocabulary
    (e.g. ``top_n`` -> a superlative token; ``negation`` -> "without"/"no"/
    "lacking") -- also D-03, checked alongside ``semantic_slots``.
    """

    name: str
    applies: Callable[..., bool]
    build_sparql: Callable[..., str]
    question_template: str
    semantic_slots: tuple[str, ...]
    intent_lexicon: tuple[str, ...]


# Ordered catalog registry -- order is the generator's deterministic
# per-shape generation order (RESEARCH "Shape Catalog" table order).
SHAPE_CATALOG: list[ShapeTemplate] = []


def _register(template: ShapeTemplate) -> ShapeTemplate:
    """Append *template* to the ordered ``SHAPE_CATALOG`` and return it.

    A small registration helper (rather than a bare list literal) keeps
    each shape's definition below self-contained and makes a future
    registration-time validation hook (e.g. "no duplicate names") a
    single, obvious place to add it.
    """
    SHAPE_CATALOG.append(template)
    return template


# --------------------------------------------------------------------------
# Small, dependency-free helpers (no pyoxigraph -- module-level safe).
# --------------------------------------------------------------------------


def _lit(value: str) -> str:
    """Render *value* as an escaped SPARQL string literal (name-anchor)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _predicates_of(index: Any) -> list[Any]:
    """The flat ``list[GroundedPredicate]`` backing *index* (same private-
    field access already established by ``test_grounding_index_builder.py``
    -- ``PredicateIndex`` has no public iterator)."""
    return list(getattr(index, "_predicates", []))


# --------------------------------------------------------------------------
# Shape 1: lookup -- ``?x rdfs:label "V" . ?x P ?result`` (a direct literal
# hop off a name-anchored subject). Schema-agnostic gate: any DatatypeProperty
# with a declared domain (an undeclared domain -- e.g. CK25's ``pv:name``/
# ``pv:id`` -- cannot be anchored, so it is correctly excluded).
# --------------------------------------------------------------------------


def _applies_lookup(pred: Any, index: Any, signals: dict[str, PredicateSignals]) -> bool:
    return pred.kind == "datatype" and bool(pred.domain)


def _build_lookup_sparql(binding: dict[str, Any]) -> str:
    # Deliberately NO ``?x a <domain_iri>`` type constraint (Rule 1 fix,
    # verified against the real CK25 data): several TBox-declared domains
    # (``pv:Product``, ``pv:Agent``) are abstract superclasses with ZERO
    # direct instances -- only their concrete subclasses (``pv:Hardware``,
    # ``pv:Employee``) are ever actually typed. Requiring the exact
    # declared domain here would silently zero out every predicate whose
    # domain is abstract (07.4-02's own documented "no instance is
    # literally typed pv:Product" finding, re-encountered at generation
    # time). The predicate + its label anchor is a sufficient, precise
    # real-world constraint -- exactly the pattern the VALIDATED spike
    # bank itself used (no domain type triple in any spike query).
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?x <{RDFS_LABEL_IRI}> {_lit(binding['filler_label'])} .\n"
        f"  ?x <{binding['predicate_iri']}> ?result .\n"
        "}"
    )


# --------------------------------------------------------------------------
# Shape 2: value_object -- ``?x rdfs:label "V" . ?x P ?mid . ?mid Q ?result``
# (the "extra hop" pattern: P's range class C has ONLY datatype-property
# children -- 07.4's ``"value_object"`` classification -- Q is one of them).
# --------------------------------------------------------------------------


def _applies_value_object(pred: Any, index: Any, signals: dict[str, PredicateSignals]) -> bool:
    return pred.shape == "value_object"


def _build_value_object_sparql(binding: dict[str, Any]) -> str:
    # Same Rule-1 fix as ``_build_lookup_sparql`` -- no domain type
    # constraint (``pv:price``'s domain ``pv:Product`` is abstract; real
    # data types the price-bearing instances ``pv:Hardware``/``pv:Service``).
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?x <{RDFS_LABEL_IRI}> {_lit(binding['filler_label'])} .\n"
        f"  ?x <{binding['predicate_iri']}> ?mid .\n"
        f"  ?mid <{binding['hop_predicate_iri']}> ?result .\n"
        "}"
    )


# --------------------------------------------------------------------------
# Shape 3: category_filter -- ``?c rdfs:label "V" . ?result P ?c`` (anchor
# the RANGE side by label; project the DOMAIN-side members). Applies to any
# predicate whose range class is a real, enumerable entity class
# (``category_instance``/``linked_entity`` -- never ``"value_object"``/
# ``"literal"``, mechanical per the 07.4 walker).
# --------------------------------------------------------------------------


def _applies_relational(pred: Any, index: Any, signals: dict[str, PredicateSignals]) -> bool:
    return pred.shape in RELATIONAL_SHAPES


def _build_category_filter_sparql(binding: dict[str, Any]) -> str:
    # RANGE side keeps its type constraint (disambiguates the label match
    # to the correct class -- the anchor). DOMAIN side deliberately has
    # NO type constraint (same Rule-1 fix as lookup/value_object): the
    # predicate itself (e.g. ``pv:hasCategory``) already selects only its
    # real-world subjects (``pv:Hardware``/``pv:Service``), and several
    # TBox-declared domains (``pv:Product``, ``pv:Agent``) are abstract
    # with zero direct instances -- matches the VALIDATED spike bank's
    # own query shape exactly (no domain type triple).
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?c a <{binding['range_iri']}> .\n"
        f"  ?c <{RDFS_LABEL_IRI}> {_lit(binding['filler_label'])} .\n"
        f"  ?result <{binding['predicate_iri']}> ?c .\n"
        "}"
    )


# --------------------------------------------------------------------------
# Shape 4: scalar_count -- same predicate pool as category_filter, COUNT
# aggregate instead of a listing (spike-proven, ck25-13).
# --------------------------------------------------------------------------


def _build_scalar_count_sparql(binding: dict[str, Any]) -> str:
    # Same RANGE-anchor-only discipline as category_filter (Rule-1 fix).
    return (
        "SELECT (COUNT(DISTINCT ?member) AS ?result) WHERE {\n"
        f"  ?c a <{binding['range_iri']}> .\n"
        f"  ?c <{RDFS_LABEL_IRI}> {_lit(binding['filler_label'])} .\n"
        f"  ?member <{binding['predicate_iri']}> ?c .\n"
        "}"
    )


# --------------------------------------------------------------------------
# Shape 5: grouped_aggregation -- ``SELECT ?result WHERE {...} GROUP BY
# ?result HAVING (COUNT(?x) > K)``. DISTINCT from scalar_count (spike
# carry-forward #2 -- the ck25-30 regression proved scalar-COUNT coverage
# does NOT cover HAVING and can distract it). K is data-bound at
# generation time (Task 2), never a hardcoded constant.
# --------------------------------------------------------------------------


def _build_grouped_aggregation_sparql(binding: dict[str, Any]) -> str:
    # No domain type constraint (same Rule-1 fix as category_filter): the
    # predicate alone determines real group membership.
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?x <{binding['predicate_iri']}> ?result .\n"
        "}\n"
        "GROUP BY ?result\n"
        f"HAVING (COUNT(?x) > {binding['threshold']})"
    )


# --------------------------------------------------------------------------
# Shapes 6/7: top_n / offset -- ``ORDER BY DESC(?v) LIMIT 1 [OFFSET 1]``.
# Requires the new Wave 0 ``orderable`` signal (a datatype predicate whose
# range is an ordered XSD type). No name-anchor slot -- the domain class
# alone provides the "member_type" context (ranks across ALL its
# instances). The generation-time strict-extremum probe (spike lesson,
# the ``weight_g``=20.0 saturation) drops ties -- implemented in Task 2.
# --------------------------------------------------------------------------


def _applies_orderable(pred: Any, index: Any, signals: dict[str, PredicateSignals]) -> bool:
    sig = signals.get(pred.iri)
    return pred.kind == "datatype" and bool(pred.domain) and bool(sig and sig.orderable)


def _build_top_n_sparql(binding: dict[str, Any]) -> str:
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?result a <{binding['domain_iri']}> .\n"
        f"  ?result <{binding['predicate_iri']}> ?v .\n"
        "}\n"
        "ORDER BY DESC(?v)\nLIMIT 1"
    )


def _build_offset_sparql(binding: dict[str, Any]) -> str:
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?result a <{binding['domain_iri']}> .\n"
        f"  ?result <{binding['predicate_iri']}> ?v .\n"
        "}\n"
        "ORDER BY DESC(?v)\nLIMIT 1 OFFSET 1"
    )


# --------------------------------------------------------------------------
# Shape 8: negation -- ``?result a C . FILTER NOT EXISTS { ?result P ?v }``.
# Requires the new Wave 0 data-driven ``optional_relation`` signal (both
# P-present and P-absent C-instances exist) -- guarantees non-empty.
# Unavailable on TBox-only ontologies (QALD, D-04) -- degrades to False,
# never crashes (Wave 0's own ``build_predicate_signals`` contract).
# --------------------------------------------------------------------------


def _applies_negation(pred: Any, index: Any, signals: dict[str, PredicateSignals]) -> bool:
    sig = signals.get(pred.iri)
    return pred.kind == "object" and bool(pred.domain) and bool(sig and sig.optional_relation)


def _build_negation_sparql(binding: dict[str, Any]) -> str:
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?result a <{binding['domain_iri']}> .\n"
        f"  FILTER NOT EXISTS {{ ?result <{binding['predicate_iri']}> ?v }}\n"
        "}"
    )


# --------------------------------------------------------------------------
# Shape 9: two_hop -- ``?c rdfs:label "V" . ?x P ?c . ?x Q ?result`` (the
# spike's richest, highest-value bucket: category_filter's range-anchor
# direction, PLUS a second forward hop off the SAME domain instance via a
# sibling predicate Q sharing P's domain). ``applies`` may consult *index*
# for a same-domain relational sibling -- still schema-agnostic (structural
# lookup, no term-name special-casing).
# --------------------------------------------------------------------------


def _applies_two_hop(pred: Any, index: Any, signals: dict[str, PredicateSignals]) -> bool:
    if pred.shape not in RELATIONAL_SHAPES:
        return False
    return any(
        other.iri != pred.iri and other.domain == pred.domain and other.shape in RELATIONAL_SHAPES
        for other in _predicates_of(index)
    )


def _build_two_hop_sparql(binding: dict[str, Any]) -> str:
    return (
        "SELECT DISTINCT ?result WHERE {\n"
        f"  ?c a <{binding['range_iri']}> .\n"
        f"  ?c <{RDFS_LABEL_IRI}> {_lit(binding['filler_label'])} .\n"
        f"  ?x <{binding['predicate_iri']}> ?c .\n"
        f"  ?x <{binding['hop_predicate_iri']}> ?result .\n"
        "}"
    )


# The 9 shapes reserved by D-02 / RESEARCH's Shape Catalog table.
# ``grouped_aggregation`` is a DISTINCT shape from ``scalar_count`` (spike
# carry-forward #2: the ck25-30 regression proved scalar-COUNT examples
# distract a HAVING case -- treating them as one shape re-introduces that
# regression risk).

_register(
    ShapeTemplate(
        name="lookup",
        applies=_applies_lookup,
        build_sparql=_build_lookup_sparql,
        question_template="What is the {predicate} of {entity}?",
        semantic_slots=("entity", "predicate"),
        intent_lexicon=(),
    )
)

_register(
    ShapeTemplate(
        name="value_object",
        applies=_applies_value_object,
        build_sparql=_build_value_object_sparql,
        question_template="What is the {predicate} {hop_predicate} of {entity}?",
        semantic_slots=("entity", "predicate", "hop_predicate"),
        intent_lexicon=(),
    )
)

_register(
    ShapeTemplate(
        name="category_filter",
        applies=_applies_relational,
        build_sparql=_build_category_filter_sparql,
        question_template="Which {member_type} are in the {category} category?",
        semantic_slots=("category", "member_type"),
        intent_lexicon=(),
    )
)

_register(
    ShapeTemplate(
        name="scalar_count",
        applies=_applies_relational,
        build_sparql=_build_scalar_count_sparql,
        question_template="How many {member_type} are there for {category}?",
        semantic_slots=("category", "member_type"),
        intent_lexicon=("how many", "number of", "count"),
    )
)

_register(
    ShapeTemplate(
        name="grouped_aggregation",
        applies=_applies_relational,
        build_sparql=_build_grouped_aggregation_sparql,
        question_template="Which {group_type} have more than {threshold} {member_type}?",
        semantic_slots=("group_type", "member_type", "threshold"),
        intent_lexicon=("more than", "at least", "per"),
    )
)

_register(
    ShapeTemplate(
        name="top_n",
        applies=_applies_orderable,
        build_sparql=_build_top_n_sparql,
        question_template="Which {member_type} has the {superlative} {order_predicate}?",
        semantic_slots=("member_type", "order_predicate", "superlative", "direction"),
        intent_lexicon=("most", "least", "highest", "lowest", "largest", "smallest"),
    )
)

_register(
    ShapeTemplate(
        name="offset",
        applies=_applies_orderable,
        build_sparql=_build_offset_sparql,
        question_template="Which {member_type} has the {ordinal}-{superlative} {order_predicate}?",
        semantic_slots=("member_type", "order_predicate", "superlative", "ordinal", "direction"),
        intent_lexicon=("second", "third", "next", "after the"),
    )
)

_register(
    ShapeTemplate(
        name="negation",
        applies=_applies_negation,
        build_sparql=_build_negation_sparql,
        question_template="Which {member_type} do not have a {predicate}?",
        semantic_slots=("member_type", "predicate"),
        intent_lexicon=("without", "no", "lacking", "don't have", "missing"),
    )
)

_register(
    ShapeTemplate(
        name="two_hop",
        applies=_applies_two_hop,
        build_sparql=_build_two_hop_sparql,
        question_template="Which {far_type} is linked to {entity} via {near_predicate}?",
        semantic_slots=("entity", "near_predicate", "far_predicate", "far_type"),
        intent_lexicon=(),
    )
)


def generate_bank(
    ontology_ttl: str,
    data_ttl: str | None = None,
    *,
    k_paraphrases: int = 3,
    seed: int = 0,
) -> dict:
    """Emit a per-ontology few-shot bank dict from *ontology_ttl*
    (+ optional *data_ttl*) via ``SHAPE_CATALOG``'s compositional templates.

    ``ontology_ttl`` is the corpus's TBox Turtle text; ``data_ttl``, if
    given, is the instance-data Turtle used for slot sampling + the
    execution non-empty filter (TBox-only when omitted, per D-04 -- e.g.
    QALD). ``k_paraphrases`` is the D-03 paraphrase count (default 3);
    ``seed`` seeds the bounded, deterministic slot sampler (RESEARCH
    "Data-binding + execution-filter" -- reproducible regeneration).

    Task 1 status: the 9 ``SHAPE_CATALOG`` closures above are fully
    implemented; this pipeline function itself is still a signature-only
    stub -- the template-instantiation + TBox slot-filling +
    data-binding/execution-filter pipeline that calls them lands in
    Task 2 of this plan. Raises ``NotImplementedError`` unconditionally
    until then.
    """
    raise NotImplementedError("generate_bank's data-binding pipeline lands in Plan 02 Task 2")
