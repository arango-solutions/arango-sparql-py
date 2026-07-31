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
(Plan 03).

Wave 0 (this file, scaffold only): the typed ``ShapeTemplate`` dataclass
catalog + the ordered ``SHAPE_CATALOG`` registry reserving the 9
compositional shape names (D-02, RESEARCH.md's Shape Catalog), plus the
``generate_bank()`` SIGNATURE (stubbed -- raises ``NotImplementedError``;
the actual template-instantiation + slot-filling + data-binding +
paraphrase pipeline lands in Plans 02/03/04).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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


def _unimplemented_applies(*_args: Any, **_kwargs: Any) -> bool:
    """Wave 0 scaffold placeholder -- Plan 02 supplies the real per-shape
    TBox-signal gate. Conservatively returns False (matches nothing) so an
    accidental early call never fabricates a false-positive candidate."""
    return False


def _unimplemented_build_sparql(*_args: Any, **_kwargs: Any) -> str:
    """Wave 0 scaffold placeholder -- Plan 02 supplies the real per-shape
    slot-filled SPARQL renderer."""
    raise NotImplementedError("ShapeTemplate.build_sparql is implemented in Plan 02")


# The 9 shapes reserved by D-02 / RESEARCH's Shape Catalog table.
# ``grouped_aggregation`` is a DISTINCT shape from ``scalar_count`` (spike
# carry-forward #2: the ck25-30 regression proved scalar-COUNT examples
# distract a HAVING case -- treating them as one shape re-introduces that
# regression risk). Only the name/question_template/semantic_slots/
# intent_lexicon scaffolding lands here; ``applies``/``build_sparql`` are
# Wave 0 stubs -- Plan 02 fills them in per-shape.

_register(
    ShapeTemplate(
        name="lookup",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="What is the {predicate} of {entity}?",
        semantic_slots=("entity", "predicate"),
        intent_lexicon=(),
    )
)

_register(
    ShapeTemplate(
        name="value_object",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="What is the {predicate} {hop_predicate} of {entity}?",
        semantic_slots=("entity", "predicate", "hop_predicate"),
        intent_lexicon=(),
    )
)

_register(
    ShapeTemplate(
        name="category_filter",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="Which {member_type} are in the {category} category?",
        semantic_slots=("category", "member_type"),
        intent_lexicon=(),
    )
)

_register(
    ShapeTemplate(
        name="scalar_count",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="How many {member_type} are there for {category}?",
        semantic_slots=("category", "member_type"),
        intent_lexicon=("how many", "number of", "count"),
    )
)

_register(
    ShapeTemplate(
        name="grouped_aggregation",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="Which {group_type} have more than {threshold} {member_type}?",
        semantic_slots=("group_type", "member_type", "threshold"),
        intent_lexicon=("more than", "at least", "per"),
    )
)

_register(
    ShapeTemplate(
        name="top_n",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="Which {member_type} has the {superlative} {order_predicate}?",
        semantic_slots=("member_type", "order_predicate", "superlative", "direction"),
        intent_lexicon=("most", "least", "highest", "lowest", "largest", "smallest"),
    )
)

_register(
    ShapeTemplate(
        name="offset",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="Which {member_type} has the {ordinal}-{superlative} {order_predicate}?",
        semantic_slots=("member_type", "order_predicate", "superlative", "ordinal", "direction"),
        intent_lexicon=("second", "third", "next", "after the"),
    )
)

_register(
    ShapeTemplate(
        name="negation",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
        question_template="Which {member_type} do not have a {predicate}?",
        semantic_slots=("member_type", "predicate"),
        intent_lexicon=("without", "no", "lacking", "don't have", "missing"),
    )
)

_register(
    ShapeTemplate(
        name="two_hop",
        applies=_unimplemented_applies,
        build_sparql=_unimplemented_build_sparql,
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

    SIGNATURE ONLY (Wave 0 Task 2): the template-instantiation + TBox
    slot-filling + data-binding/execution-filter + paraphrase pipeline is
    implemented across Plans 02 (template backbone + CK25 bank), 03
    (data-binding + ``verify_generated_bank.py`` gate), and 04 (paraphrase
    + faithfulness guard). Raises ``NotImplementedError`` unconditionally
    until then.
    """
    raise NotImplementedError(
        "generate_bank is implemented across Plans 02-04 (Phase 07.5 Stage 1)"
    )
