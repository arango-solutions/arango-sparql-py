"""Eval-only pyoxigraph -> LabelIndex builder for CK25's vendored instance graph.

Turns a Turtle instance graph (e.g. CK25's ``raw/prod-inst.ttl``) plus a list
of prefixed label predicates (e.g. ``["rdfs:label", "pv:name"]``) into an
``arango_query_core.nl.grounding.LabelIndex`` the eval harness can inject
into ``NlPipeline`` via seam 6.

This is a near-verbatim port of
``scratchpad/nl-grounding-spike/grounding_spike.py::build_entity_index``,
restructured to return a ``LabelIndex`` instead of a bare ``list[dict]``,
and of ``tests/nl2sparql/eval/runner.py::_build_label_map``'s
query/normalization shape.

Packaging boundary (CLAUDE.md hard rule 5): this file MUST live under
``tests/`` and MUST NOT be imported by ``arango_query_core``/``arango_sparql``
proper. Every ``pyoxigraph``-touching import stays function-local (never at
module top level) so those packages never gain a transitive ``pyoxigraph``
import path -- mirroring ``runner.py::_build_label_map``'s own
``from tests.helpers.oxi import oxi_query`` placement.
"""

from __future__ import annotations

# Known ontology prefixes used by CK25's corpus.yml (and the spike's literal
# PREFIX preamble) -- expanding prefixed label_predicates against this map
# keeps the query construction independent of any particular Turtle prefix
# declaration order.
_PREFIXES = {
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "pv": "http://ld.company.org/prod-vocab/",
    "prodi": "http://ld.company.org/prod-instances/",
}


def _expand_predicate(predicate: str) -> str:
    """Expand a prefixed name (``"rdfs:label"``) to a full IRI.

    Predicates already given as full IRIs (``<...>`` or ``http://...``) pass
    through unchanged.
    """
    if predicate.startswith("<") or predicate.startswith("http://") or predicate.startswith("https://"):
        return predicate.strip("<>")
    prefix, _, local = predicate.partition(":")
    if not local or prefix not in _PREFIXES:
        raise ValueError(f"unknown label predicate prefix: {predicate!r}")
    return f"{_PREFIXES[prefix]}{local}"


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


def build_label_index(data_ttl: str, label_predicates: list[str]):
    """Build a ``LabelIndex`` from a Turtle instance graph.

    ``data_ttl`` is the raw Turtle text (e.g. CK25's ``raw/prod-inst.ttl``
    contents); ``label_predicates`` is a list of prefixed or full-IRI
    predicates whose objects are treated as human-readable labels (e.g.
    ``["rdfs:label", "pv:name"]``).

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
    predicate_union = "|".join(f"<{_expand_predicate(p)}>" for p in label_predicates)
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
        label = (row.get("label") or "").strip('"').split('"^^')[0]
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
