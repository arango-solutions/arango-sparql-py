"""Eval-only pyoxigraph -> LabelIndex/PredicateIndex builders.

``build_label_index`` turns a Turtle *instance* graph (e.g. CK25's
``raw/prod-inst.ttl``) plus a list of prefixed label predicates (e.g.
``["rdfs:label", "pv:name"]``) into an
``arango_query_core.nl.grounding.LabelIndex`` the eval harness can inject
into ``NlPipeline`` via seam 6 (entity/instance grounding, Phase 07.3).

``build_predicate_index`` (Phase 07.4, sibling function) is the inverse
walk: it turns a Turtle *TBox* (e.g. a corpus's ``ontology:`` block --
``shared_ontology`` in ``runner.py``) into an
``arango_query_core.nl.grounding.PredicateIndex`` of
``GroundedPredicate``s with a mechanically-derived usage ``shape``
(``"value_object"`` / ``"category_instance"`` / ``"linked_entity"`` /
``"literal"``), injected via seam 7 (predicate/schema-convention
grounding).

``build_label_index`` is a near-verbatim port of
``scratchpad/nl-grounding-spike/grounding_spike.py::build_entity_index``,
restructured to return a ``LabelIndex`` instead of a bare ``list[dict]``,
and of ``tests/nl2sparql/eval/runner.py::_build_label_map``'s
query/normalization shape.

Packaging boundary (CLAUDE.md hard rule 5): this file MUST live under
``tests/`` and MUST NOT be imported by ``arango_query_core``/``arango_sparql``
proper. Every ``pyoxigraph``-touching import stays function-local (never at
module top level) so those packages never gain a transitive ``pyoxigraph``
import path -- mirroring ``runner.py::_build_label_map``'s own
``from tests.helpers.oxi import oxi_query`` placement. This applies equally
to ``build_predicate_index`` (D-08).
"""

from __future__ import annotations

# WR-01: built-in prefixes for CK25's own vocabulary (and the ``rdfs``
# prefix every corpus needs). This is a DEFAULT, not the only place a
# dataset can register a prefix: `build_label_index`'s `prefixes` parameter
# lets a corpus config (`grounding.prefixes:` in configs.yml) extend/
# override this map without a code change here, so a future corpus (CDF or
# otherwise) that lists a prefixed predicate under a prefix this file
# doesn't know is a config-only edit, not a code-only one.
_PREFIXES = {
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "pv": "http://ld.company.org/prod-vocab/",
    "prodi": "http://ld.company.org/prod-instances/",
}


def _expand_predicate(predicate: str, prefixes: dict[str, str] | None = None) -> str:
    """Expand a prefixed name (``"rdfs:label"``) to a full IRI.

    Predicates already given as full IRIs (``<...>`` or ``http://...``) pass
    through unchanged. ``prefixes`` (WR-01), if given, is merged over the
    built-in ``_PREFIXES`` default -- letting a caller (e.g. a corpus's
    ``grounding.prefixes:`` config entry) register additional/overriding
    prefixes without editing this file.
    """
    if predicate.startswith("<") or predicate.startswith("http://") or predicate.startswith("https://"):
        return predicate.strip("<>")
    effective_prefixes = {**_PREFIXES, **(prefixes or {})}
    prefix, _, local = predicate.partition(":")
    if not local or prefix not in effective_prefixes:
        raise ValueError(f"unknown label predicate prefix: {predicate!r}")
    return f"{effective_prefixes[prefix]}{local}"


# CR-01: W3C-standard ontology-header vocabulary terms (RDFS/OWL/void) used
# to recognize SCHEMA-level subjects (classes/properties/ontology headers)
# so they can be excluded from the instance-level "Known entities" index
# below. These are well-known, dataset-INDEPENDENT RDF vocabulary IRIs --
# never a CK25- (or any corpus-) specific term -- so hardcoding them here
# does not reintroduce the "dataset-specific stuff hardcoded outside
# label_predicates" pitfall WR-01 warns about; it keeps the exclusion
# schema-agnostic (works for CDF too).
_SCHEMA_TYPES = (
    "http://www.w3.org/2002/07/owl#Class",
    "http://www.w3.org/2000/01/rdf-schema#Class",
    "http://www.w3.org/2002/07/owl#ObjectProperty",
    "http://www.w3.org/2002/07/owl#DatatypeProperty",
    "http://www.w3.org/2002/07/owl#AnnotationProperty",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
    "http://www.w3.org/2002/07/owl#Ontology",
    "http://rdfs.org/ns/void#Dataset",
)


def build_label_index(
    data_ttl: str,
    label_predicates: list[str],
    prefixes: dict[str, str] | None = None,
):
    """Build a ``LabelIndex`` from a Turtle instance graph.

    ``data_ttl`` is the raw Turtle text (e.g. CK25's ``raw/prod-inst.ttl``
    contents); ``label_predicates`` is a list of prefixed or full-IRI
    predicates whose objects are treated as human-readable labels (e.g.
    ``["rdfs:label", "pv:name"]``). ``prefixes`` (WR-01) optionally extends/
    overrides the built-in ``_PREFIXES`` default used to resolve those
    prefixed predicates -- e.g. a future corpus's ``grounding.prefixes:``
    config entry -- so a new vocabulary prefix is a config-only edit, not a
    code change to this file.

    Aggregates by subject IRI into ``{labels: set, type: local-name}``, then
    returns ``LabelIndex.from_items([GroundedEntity(...), ...])``.

    CR-01: the query excludes SCHEMA-level subjects (ontology classes,
    properties, and the ontology/dataset header itself) from the result --
    those carry ``rdfs:label``/``pv:name`` too (e.g. CK25's vocab header
    ``pv:`` labeled ``"pv: Products - Vocab"@en``, or ``pv:Manager``/
    ``pv:hasManager``) but are not groundable named individuals. A subject
    is excluded if (a) it is explicitly typed as one of the well-known
    ``_SCHEMA_TYPES`` above, (b) it is ever used as an ``rdf:type`` object
    (i.e. something is declared an instance of it -- the hallmark of a
    class), or (c) it is ever used as a predicate (the hallmark of a
    property) -- (b)/(c) are structural, so they also catch schema terms
    typed with a vocabulary this file doesn't enumerate.
    """
    from tests.helpers.oxi import load_store_from_string, oxi_query

    store = load_store_from_string(data_ttl)
    predicate_union = "|".join(f"<{_expand_predicate(p, prefixes)}>" for p in label_predicates)
    schema_type_filters = "\n      ".join(f"FILTER NOT EXISTS {{ ?s a <{t}> }}" for t in _SCHEMA_TYPES)
    query = f"""
    SELECT ?s ?label ?type WHERE {{
      ?s ({predicate_union}) ?label .
      {schema_type_filters}
      FILTER NOT EXISTS {{ ?anyInstance a ?s }}
      FILTER NOT EXISTS {{ ?anySubject ?s ?anyObject }}
      OPTIONAL {{ ?s a ?type }}
    }}"""

    by_iri: dict[str, dict] = {}
    for row in oxi_query(store, query).rows or []:
        subj = row.get("s")
        if not subj:
            continue
        iri = subj[1:-1] if subj.startswith("<") and subj.endswith(">") else subj
        # CR-02: split off the "^^<datatype>"/"@lang envelope BEFORE
        # stripping the surrounding quotes (mirrors runner.py's
        # `_strip_execution_literal`) -- stripping quotes first corrupts
        # language-tagged labels, e.g. '"Country"@en' -> 'Country"@en'
        # (the trailing quote survives because `n` is the string's last
        # character, not `"`).
        label = (row.get("label") or "").split('"^^')[0].strip('"').split('"@')[0]
        entity = by_iri.setdefault(iri, {"labels": set(), "type": ""})
        if label:
            entity["labels"].add(label)
        raw_type = row.get("type")
        if raw_type and not entity["type"]:
            entity["type"] = raw_type.rsplit("/", 1)[-1].rstrip(">")

    from arango_query_core.nl.grounding import GroundedEntity, LabelIndex

    return LabelIndex.from_items(
        [
            GroundedEntity(id=iri, labels=tuple(v["labels"]), type=v["type"])
            for iri, v in by_iri.items()
        ]
    )


def _strip_iri(term: str | None) -> str:
    """Strip pyoxigraph's ``<...>`` N-Triples envelope from a NamedNode term.

    Returns ``""`` for ``None``/unbound (mirrors ``OPTIONAL``'s "absent" case
    rather than raising), so callers can treat "not declared" uniformly.
    """
    if not term:
        return ""
    return term[1:-1] if term.startswith("<") and term.endswith(">") else term


def _local_name(term: str | None) -> str:
    """IRI (or ``<...>``-wrapped IRI) -> its trailing local name.

    Tries the fragment (``#foo``) first, then the last path segment
    (``/foo``) -- the same two IRI shapes CK25/QALD's vocabularies use
    (``http://.../prod-vocab/Price`` has no ``#``; a hypothetical
    ``http://example.org/onto#Price`` would). ``""`` in, ``""`` out.
    """
    iri = _strip_iri(term)
    if not iri:
        return ""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def build_predicate_index(ontology_ttl: str):
    """Build a ``PredicateIndex`` from a Turtle TBox (D-02, mechanical only).

    ``ontology_ttl`` is the raw Turtle text of a corpus's ``ontology:``
    block (``shared_ontology`` in ``runner.py`` -- every corpus has one,
    unlike ``build_label_index``'s ``data_ttl`` which only CK25-shaped
    corpora vendor). Walks every declared ``owl:ObjectProperty``/
    ``owl:DatatypeProperty`` and classifies each predicate's rendering
    ``shape`` purely from its own ``rdfs:domain``/``rdfs:range``
    declarations -- **no hand-authored, per-schema hints** (D-02): this
    file must never special-case any single vocabulary term's own name
    anywhere in the classification logic below, or the lever stops
    transferring to a new schema (e.g. CDF).

    Two-pass query (RESEARCH.md Pattern 2), same "one clear query per
    pass, function-local pyoxigraph import" discipline as
    ``build_label_index`` above:

    - Pass 1 selects every declared property with its own
      ``rdfs:label``/``rdfs:domain``/``rdfs:range`` (``BIND``-tagged
      ``"object"``/``"datatype"`` kind).
    - Pass 2 runs once per distinct object-property range class ``C``,
      selecting ``C``'s "children" -- properties with an **explicitly
      declared** ``rdfs:domain == C`` (exact match only; this file MUST
      NOT walk any class-hierarchy inheritance predicate here -- see
      RESEARCH.md's ``pv:Employee``/``pv:Agent`` false-positive
      walkthrough for why an inheritance-aware walk would over-fire).

    Corrected 3-way shape rule (RESEARCH.md Pattern 1, verified against
    the real CK25 TBox -- see RESEARCH.md's worked example for the
    three discriminating properties):

    - ``kind == "datatype"`` -> ``shape = "literal"``.
    - ``kind == "object"``, range class ``C``'s children are non-empty
      AND every child is a ``DatatypeProperty`` -> ``shape =
      "value_object"`` (``shape_detail`` carries the ``(label, range)``
      pairs of those datatype children -- the "extra hop" example the
      prompt renderer needs).
    - ``kind == "object"``, ``C`` has zero children (this also covers
      the case where ``C`` itself is undeclared/unbound -- an
      undeclared range trivially has no domain-matched children
      either, so it degrades to this branch, not a crash; QALD's
      DBpedia subset exercises exactly this path, see Task 3) ->
      ``shape = "category_instance"``.
    - Otherwise (``C`` has >=1 non-datatype child, e.g. ``pv:Manager``'s
      ``pv:hasDirectReport``) -> ``shape = "linked_entity"`` (the false-
      positive guard: a naive "range class has >=1 own property" rule
      would wrongly flag this as ``value_object``, identical to
      ``pv:price``).
    """
    from tests.helpers.oxi import load_store_from_string, oxi_query

    store = load_store_from_string(ontology_ttl)

    def _clean(raw: str | None) -> str:
        # Reuses CR-02's exact normalization (see build_label_index above):
        # split off the "^^<datatype>"/"@lang envelope BEFORE stripping
        # quotes, and also handles BIND-produced plain literals (e.g.
        # '"object"', no envelope at all) via the same chained splits.
        return (raw or "").split('"^^')[0].strip('"').split('"@')[0]

    pass1_query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?p ?kind ?label ?domain ?range WHERE {
      { ?p a owl:ObjectProperty . BIND("object" AS ?kind) }
      UNION
      { ?p a owl:DatatypeProperty . BIND("datatype" AS ?kind) }
      OPTIONAL { ?p rdfs:label ?label }
      OPTIONAL { ?p rdfs:domain ?domain }
      OPTIONAL { ?p rdfs:range ?range }
    }"""

    # iri -> {kind, label, domain, range, range_iri}. ``range`` is the
    # local name (rendered in the prompt); ``range_iri`` is the full IRI
    # (used as Pass 2's join key, and to detect "range declared at all").
    declared: dict[str, dict[str, str]] = {}
    for row in oxi_query(store, pass1_query).rows or []:
        iri = _strip_iri(row.get("p"))
        if not iri:
            continue
        range_term = row.get("range")
        declared[iri] = {
            "kind": _clean(row.get("kind")),
            "label": _clean(row.get("label")) or _local_name(iri),
            "domain": _local_name(row.get("domain")),
            "range": _local_name(range_term),
            "range_iri": _strip_iri(range_term),
        }

    # Pass 2: once per distinct object-property range class C (never
    # per-predicate -- CK25 has 14 classes, QALD's subset has 75; both
    # trivial against an in-memory store).
    range_classes = {p["range_iri"] for p in declared.values() if p["kind"] == "object" and p["range_iri"]}
    children_by_class: dict[str, list[dict[str, str]]] = {}
    for class_iri in range_classes:
        pass2_query = f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?childP ?childKind ?childLabel ?childRange WHERE {{
          {{ ?childP a owl:ObjectProperty ; rdfs:domain <{class_iri}> . BIND("object" AS ?childKind) }}
          UNION
          {{ ?childP a owl:DatatypeProperty ; rdfs:domain <{class_iri}> . BIND("datatype" AS ?childKind) }}
          OPTIONAL {{ ?childP rdfs:label ?childLabel }}
          OPTIONAL {{ ?childP rdfs:range ?childRange }}
        }}"""
        children = []
        for row in oxi_query(store, pass2_query).rows or []:
            children.append(
                {
                    "kind": _clean(row.get("childKind")),
                    "label": _clean(row.get("childLabel")) or _local_name(row.get("childP")),
                    "range": _local_name(row.get("childRange")),
                }
            )
        children_by_class[class_iri] = children

    from arango_query_core.nl.grounding import GroundedPredicate, PredicateIndex

    items = []
    for iri, p in declared.items():
        if p["kind"] == "datatype":
            shape, shape_detail = "literal", ()
        else:
            children = children_by_class.get(p["range_iri"], [])
            if children and all(c["kind"] == "datatype" for c in children):
                shape = "value_object"
                shape_detail = tuple((c["label"], c["range"]) for c in children)
            elif not children:
                shape, shape_detail = "category_instance", ()
            else:
                shape, shape_detail = "linked_entity", ()
        items.append(
            GroundedPredicate(
                iri=iri,
                label=p["label"],
                kind=p["kind"],
                domain=p["domain"],
                range=p["range"],
                shape=shape,
                shape_detail=shape_detail,
            )
        )

    return PredicateIndex.from_items(items)
