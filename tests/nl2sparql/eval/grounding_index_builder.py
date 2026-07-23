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


def build_label_index(data_ttl: str, label_predicates: list[str]):
    """Build a ``LabelIndex`` from a Turtle instance graph.

    ``data_ttl`` is the raw Turtle text (e.g. CK25's ``raw/prod-inst.ttl``
    contents); ``label_predicates`` is a list of prefixed or full-IRI
    predicates whose objects are treated as human-readable labels (e.g.
    ``["rdfs:label", "pv:name"]``).

    Aggregates by subject IRI into ``{labels: set, type: local-name}``, then
    returns ``LabelIndex.from_items([GroundedEntity(...), ...])``.
    """
    from tests.helpers.oxi import load_store_from_string, oxi_query

    store = load_store_from_string(data_ttl)
    predicate_union = "|".join(f"<{_expand_predicate(p)}>" for p in label_predicates)
    query = f"""
    SELECT ?s ?label ?type WHERE {{
      ?s ({predicate_union}) ?label .
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
