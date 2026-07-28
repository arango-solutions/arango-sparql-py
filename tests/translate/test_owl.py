"""Unit tests for :mod:`arango_sparql.translate.owl`.

Coverage goals:

* Round-trip — Turtle → :class:`MappingBundle` → Turtle preserves
  the entity/relationship semantics that the resolver consumes.
* Phys vocabulary — every documented ``phys:*`` annotation maps to
  the correct bundle field on import.
* OWL-bomb defences (PRD §8.6 T7) — the module-level triple cap
  fires when exceeded, both via the explicit ``max_triples`` kwarg
  and via the ``MAPPING_IMPORT_MAX_TRIPLES`` env var.
* Malformed input — non-Turtle bytes raise
  :class:`OwlParseError` with the typed code ``E_OWL_PARSE``.
* Empty / None input — degrade gracefully.
* Source provenance — bundles imported via :func:`turtle_to_mapping`
  are stamped with ``source.kind = "imported_owl"``.
* Both ``phys:`` namespaces — annotations using the legacy and the
  current spelling round-trip identically.
"""

from __future__ import annotations

from typing import Any

import pytest
from rdflib import Graph

from arango_sparql.translate.mapping import MappingBundle, MappingSource
from arango_sparql.translate.owl import (
    DEFAULT_MAPPING_IMPORT_MAX_TRIPLES,
    MAPPING_IMPORT_MAX_TRIPLES_ENV,
    OwlBombError,
    OwlParseError,
    count_triples,
    format_from_mime,
    mapping_to_turtle,
    owl_graph_view,
    parse_owl_graph,
    resolve_max_triples,
    turtle_to_mapping,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PG_TURTLE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://ex.org/> .

ex:Person a owl:Class ;
    phys:collectionName "Person" ;
    phys:mappingStyle "COLLECTION" .

ex:Org a owl:Class ;
    phys:collectionName "Org" ;
    phys:mappingStyle "COLLECTION" .

ex:knows a owl:ObjectProperty ;
    phys:edgeCollectionName "knows" ;
    phys:mappingStyle "DEDICATED_COLLECTION" ;
    rdfs:domain ex:Person ;
    rdfs:range  ex:Person .

ex:worksAt a owl:ObjectProperty ;
    phys:edgeCollectionName "worksAt" ;
    rdfs:domain ex:Person ;
    rdfs:range  ex:Org .
"""


LPG_TURTLE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix ex:   <http://ex.org/> .

ex:Person a owl:Class ;
    phys:collectionName "entities" ;
    phys:mappingStyle "LABEL" ;
    phys:typeField "kind" ;
    phys:typeValue "person" .

ex:knows a owl:ObjectProperty ;
    phys:edgeCollectionName "edges" ;
    phys:mappingStyle "GENERIC_WITH_TYPE" ;
    phys:typeField "rel" ;
    phys:typeValue "knows" .
"""


RPT_TURTLE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix ex:   <http://ex.org/> .

ex:Triple a owl:Class ;
    phys:triplesCollection "_triples" ;
    phys:mappingStyle "RPT" ;
    phys:subjectColumn "subject_uri" ;
    phys:predicateColumn "predicate" ;
    phys:objectUriColumn "object_uri" ;
    phys:objectValueColumn "object_value" .
"""


TENANT_TURTLE = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix ex:   <http://ex.org/> .

ex:Account a owl:Class ;
    phys:collectionName "Account" ;
    phys:mappingStyle "COLLECTION" ;
    phys:tenantField "org_id" ;
    phys:tenantEntity "Org" .
"""


# ---------------------------------------------------------------------------
# Happy-path round-trip
# ---------------------------------------------------------------------------


def test_turtle_to_mapping_pg_entities_and_relationships() -> None:
    bundle = turtle_to_mapping(PG_TURTLE)
    entities = bundle.entities()
    relationships = bundle.relationships()

    assert set(entities) == {"Person", "Org"}
    assert entities["Person"]["collectionName"] == "Person"
    assert entities["Person"]["style"] == "COLLECTION"
    assert entities["Org"]["collectionName"] == "Org"

    assert set(relationships) == {"knows", "worksAt"}
    assert relationships["knows"]["edgeCollectionName"] == "knows"
    assert relationships["knows"]["style"] == "DEDICATED_COLLECTION"
    assert relationships["knows"]["fromEntity"] == "Person"
    assert relationships["knows"]["toEntity"] == "Person"
    assert relationships["worksAt"]["fromEntity"] == "Person"
    assert relationships["worksAt"]["toEntity"] == "Org"


def test_turtle_to_mapping_lpg_typeField_typeValue() -> None:
    bundle = turtle_to_mapping(LPG_TURTLE)
    person = bundle.entities()["Person"]
    assert person["style"] == "LABEL"
    assert person["typeField"] == "kind"
    assert person["typeValue"] == "person"

    knows = bundle.relationships()["knows"]
    assert knows["style"] == "GENERIC_WITH_TYPE"
    assert knows["typeField"] == "rel"
    assert knows["typeValue"] == "knows"


def test_turtle_to_mapping_rpt_columns() -> None:
    bundle = turtle_to_mapping(RPT_TURTLE)
    triple = bundle.entities()["Triple"]
    assert triple["style"] == "RPT"
    assert triple["triplesCollection"] == "_triples"
    assert triple["subjectColumn"] == "subject_uri"
    assert triple["predicateColumn"] == "predicate"
    assert triple["objectUriColumn"] == "object_uri"
    assert triple["objectValueColumn"] == "object_value"


def test_turtle_to_mapping_tenant_annotations() -> None:
    bundle = turtle_to_mapping(TENANT_TURTLE)
    account = bundle.entities()["Account"]
    assert account["tenantField"] == "org_id"
    assert account["tenantEntity"] == "Org"


def test_turtle_to_mapping_preserves_owl_turtle() -> None:
    bundle = turtle_to_mapping(PG_TURTLE)
    assert bundle.owl_turtle == PG_TURTLE


def test_turtle_to_mapping_preserve_owl_false_drops_turtle() -> None:
    bundle = turtle_to_mapping(PG_TURTLE, preserve_owl=False)
    assert bundle.owl_turtle is None


def test_turtle_to_mapping_stamps_imported_owl_source() -> None:
    bundle = turtle_to_mapping(PG_TURTLE, source_notes="UI upload")
    assert bundle.source is not None
    assert bundle.source.kind == "imported_owl"
    assert bundle.source.notes == "UI upload"


def test_turtle_to_mapping_records_triple_count_in_metadata() -> None:
    bundle = turtle_to_mapping(PG_TURTLE)
    g = Graph()
    g.parse(data=PG_TURTLE, format="turtle")
    assert bundle.metadata["tripleCount"] == count_triples(g)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_via_owl_turtle_returns_verbatim() -> None:
    """When a bundle carries inline owl_turtle, mapping_to_turtle
    must return it unchanged — the analyzer's serialisation is the
    canonical form and re-rendering would introduce drift.
    """

    bundle = turtle_to_mapping(PG_TURTLE)
    assert mapping_to_turtle(bundle) == PG_TURTLE


def test_round_trip_via_synthesizer_preserves_entities() -> None:
    """When a bundle has no inline owl_turtle, mapping_to_turtle
    synthesises Turtle from physical_mapping. Re-importing the
    output must round-trip the entity / relationship surface.
    """

    original = turtle_to_mapping(PG_TURTLE, preserve_owl=False)
    ttl = mapping_to_turtle(original)
    re_imported = turtle_to_mapping(ttl)
    assert set(re_imported.entities()) == set(original.entities())
    assert set(re_imported.relationships()) == set(original.relationships())


def test_round_trip_preserves_rpt_columns_via_synthesizer() -> None:
    original = turtle_to_mapping(RPT_TURTLE, preserve_owl=False)
    ttl = mapping_to_turtle(original)
    re_imported = turtle_to_mapping(ttl)
    triple = re_imported.entities()["Triple"]
    # The synthesiser preserves all phys:* columns we put on the
    # graph; round-trip must not lose any of them.
    for slot in (
        "triplesCollection",
        "subjectColumn",
        "predicateColumn",
        "objectUriColumn",
        "objectValueColumn",
    ):
        assert triple.get(slot) == original.entities()["Triple"].get(slot)


def test_mapping_to_turtle_rejects_none() -> None:
    from arango_sparql.translate.mapping import MappingError

    with pytest.raises(MappingError):
        mapping_to_turtle(None)


def test_mapping_to_turtle_synthesises_from_bundle_without_owl() -> None:
    """Synthetic export from a hand-built bundle without inline
    Turtle should still produce a valid OWL/Turtle document.
    """

    bundle = MappingBundle(
        physical_mapping={
            "entities": {"Person": {"style": "COLLECTION", "collectionName": "Person"}},
            "relationships": {},
        },
        source=MappingSource(kind="manual", notes="hand built"),
    )
    ttl = mapping_to_turtle(bundle)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    assert len(g) > 0
    re_imported = turtle_to_mapping(ttl)
    assert "Person" in re_imported.entities()


# ---------------------------------------------------------------------------
# Two phys: namespaces
# ---------------------------------------------------------------------------


def test_legacy_phys_namespace_is_accepted() -> None:
    """The historical
    ``https://arango-schema-mapper.example.org/phys#`` namespace is
    one of the two accepted ``phys:`` spellings (see
    :data:`arango_sparql.translate.resolver._PHYS_NAMESPACES`).
    Importing OWL that uses it must round-trip identically to the
    canonical spelling.
    """

    legacy_ttl = """
    @prefix owl:  <http://www.w3.org/2002/07/owl#> .
    @prefix phys: <https://arango-schema-mapper.example.org/phys#> .
    @prefix ex:   <http://ex.org/> .

    ex:Person a owl:Class ;
        phys:collectionName "Person" ;
        phys:mappingStyle "COLLECTION" .
    """
    bundle = turtle_to_mapping(legacy_ttl)
    person = bundle.entities()["Person"]
    assert person["collectionName"] == "Person"
    assert person["style"] == "COLLECTION"


# ---------------------------------------------------------------------------
# OWL-bomb defences (PRD §8.6 T7)
# ---------------------------------------------------------------------------


def test_triple_cap_fires_via_explicit_kwarg() -> None:
    """The default cap is generous; we override it to a tiny
    value so a small fixture fires the cap.
    """

    g = Graph()
    g.parse(data=PG_TURTLE, format="turtle")
    actual_triples = count_triples(g)
    cap = max(1, actual_triples - 1)
    with pytest.raises(OwlBombError) as exc_info:
        turtle_to_mapping(PG_TURTLE, max_triples=cap)
    assert exc_info.value.code == "E_OWL_TOO_LARGE"
    assert MAPPING_IMPORT_MAX_TRIPLES_ENV in str(exc_info.value)


def test_triple_cap_fires_via_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MAPPING_IMPORT_MAX_TRIPLES_ENV, "3")
    with pytest.raises(OwlBombError):
        turtle_to_mapping(PG_TURTLE)


def test_triple_cap_default_allows_normal_fixtures() -> None:
    """The 200 000-triple default must not flag any of the small
    test fixtures — sanity check so a regression in
    ``DEFAULT_MAPPING_IMPORT_MAX_TRIPLES`` (someone makes it 1)
    fails loudly here.
    """

    bundle = turtle_to_mapping(PG_TURTLE)
    assert bundle.metadata["tripleCount"] < DEFAULT_MAPPING_IMPORT_MAX_TRIPLES


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("100", 100),
        ("0", DEFAULT_MAPPING_IMPORT_MAX_TRIPLES),
        ("-5", DEFAULT_MAPPING_IMPORT_MAX_TRIPLES),
        ("garbage", DEFAULT_MAPPING_IMPORT_MAX_TRIPLES),
        ("", DEFAULT_MAPPING_IMPORT_MAX_TRIPLES),
        ("   ", DEFAULT_MAPPING_IMPORT_MAX_TRIPLES),
    ],
)
def test_resolve_max_triples_env_parsing(monkeypatch: pytest.MonkeyPatch, raw: str, expected: int) -> None:
    monkeypatch.setenv(MAPPING_IMPORT_MAX_TRIPLES_ENV, raw)
    assert resolve_max_triples() == expected


def test_resolve_max_triples_explicit_override_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MAPPING_IMPORT_MAX_TRIPLES_ENV, "999")
    assert resolve_max_triples(42) == 42


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


def test_malformed_turtle_raises_owl_parse_error() -> None:
    with pytest.raises(OwlParseError) as exc_info:
        turtle_to_mapping("@prefix this is not valid Turtle")
    assert exc_info.value.code == "E_OWL_PARSE"


def test_non_string_input_raises_parse_error() -> None:
    with pytest.raises(OwlParseError):
        turtle_to_mapping(None)  # type: ignore[arg-type]


def test_empty_string_raises_parse_error() -> None:
    with pytest.raises(OwlParseError):
        turtle_to_mapping("")


def test_well_formed_but_empty_owl_returns_empty_bundle() -> None:
    """Valid Turtle that declares zero entities should produce a
    bundle with empty physicalMapping rather than raising.
    """

    bundle = turtle_to_mapping("@prefix x: <http://x/> .")
    assert bundle.entities() == {}
    assert bundle.relationships() == {}
    assert bundle.source is not None
    assert bundle.source.kind == "imported_owl"


# ---------------------------------------------------------------------------
# Validation warnings (defer-rather-than-raise)
# ---------------------------------------------------------------------------


def test_invalid_collection_name_emits_warning_not_error() -> None:
    """OWL with a phys:collectionName that fails the validator
    should still import (so a partially-mapped ontology is usable)
    but emit a W_SCHEMA_INVALID_COLLECTION warning.
    """

    bad_ttl = """
    @prefix owl:  <http://www.w3.org/2002/07/owl#> .
    @prefix phys: <https://arango.solutions/phys#> .
    @prefix ex:   <http://ex.org/> .

    ex:Person a owl:Class ;
        phys:collectionName "has a space and !!" ;
        phys:mappingStyle "COLLECTION" .
    """
    bundle = turtle_to_mapping(bad_ttl)
    warnings: list[dict[str, Any]] = bundle.metadata.get("warnings") or []
    assert any(w["code"] == "W_SCHEMA_INVALID_COLLECTION" for w in warnings)
    # And the entity is still present so the user can edit it.
    assert "Person" in bundle.entities()


def test_invalid_field_name_on_relationship_emits_warning() -> None:
    """Field names that contain backticks or control characters
    would let an attacker break out of the ```` `quoted` ```` AQL
    literal, so :func:`is_valid_field_name` rejects them. The
    importer should surface the rejection as a warning rather than
    failing the whole import (defer-rather-than-raise posture so a
    partially-mapped ontology is still inspectable in the UI).
    """

    # Embed an actual backtick (the value AQL would refuse to quote)
    # via Turtle escaping; ``\u0060`` is the backtick code point.
    bad_ttl = (
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix phys: <https://arango.solutions/phys#> .\n"
        "@prefix ex:   <http://ex.org/> .\n"
        "\n"
        "ex:knows a owl:ObjectProperty ;\n"
        '    phys:edgeCollectionName "knows" ;\n'
        '    phys:typeField "bad\\u0060field" .\n'
    )
    bundle = turtle_to_mapping(bad_ttl)
    warnings = bundle.metadata.get("warnings") or []
    assert any(w["code"] == "W_SCHEMA_INVALID_FIELD" for w in warnings)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_owl_class_without_explicit_style_defaults_to_collection() -> None:
    ttl = """
    @prefix owl:  <http://www.w3.org/2002/07/owl#> .
    @prefix phys: <https://arango.solutions/phys#> .
    @prefix ex:   <http://ex.org/> .

    ex:Person a owl:Class ;
        phys:collectionName "Person" .
    """
    bundle = turtle_to_mapping(ttl)
    assert bundle.entities()["Person"]["style"] == "COLLECTION"


def test_object_property_without_explicit_style_defaults_to_dedicated() -> None:
    ttl = """
    @prefix owl:  <http://www.w3.org/2002/07/owl#> .
    @prefix phys: <https://arango.solutions/phys#> .
    @prefix ex:   <http://ex.org/> .

    ex:knows a owl:ObjectProperty ;
        phys:edgeCollectionName "knows" .
    """
    bundle = turtle_to_mapping(ttl)
    assert bundle.relationships()["knows"]["style"] == "DEDICATED_COLLECTION"


def test_datatype_property_is_not_a_relationship() -> None:
    """owl:DatatypeProperty resources belong on the entity side,
    not as relationships. Importer must skip them.
    """

    ttl = """
    @prefix owl:  <http://www.w3.org/2002/07/owl#> .
    @prefix ex:   <http://ex.org/> .

    ex:name a owl:DatatypeProperty .
    """
    bundle = turtle_to_mapping(ttl)
    assert bundle.relationships() == {}


def test_count_triples_matches_rdflib_len() -> None:
    g = Graph()
    g.parse(data=PG_TURTLE, format="turtle")
    assert count_triples(g) == len(g)


# ---------------------------------------------------------------------------
# owl_graph_view — OWL/Turtle → UI schema-graph shape
# ---------------------------------------------------------------------------


_GRAPH_VIEW_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/> .

ex:Person a owl:Class ; rdfs:comment "A person" .
ex:Org a owl:Class .
ex:Employee a owl:Class ; rdfs:subClassOf ex:Person .
ex:knows a owl:ObjectProperty ; rdfs:domain ex:Person ; rdfs:range ex:Person .
ex:worksAt a owl:ObjectProperty ; rdfs:domain ex:Person ; rdfs:range ex:Org .
ex:name a owl:DatatypeProperty ; rdfs:domain ex:Person ; rdfs:range rdfs:Literal .
ex:note a owl:AnnotationProperty ; rdfs:domain ex:Org .
"""


def test_graph_view_projects_classes_with_supers_and_comments() -> None:
    view = owl_graph_view(_GRAPH_VIEW_TTL)
    by_name = {c["localName"]: c for c in view["classes"]}
    assert set(by_name) == {"Person", "Org", "Employee"}
    assert by_name["Person"]["comment"] == "A person"
    # subClassOf is captured as a full IRI list.
    assert by_name["Employee"]["superClasses"] == ["http://example.org/Person"]
    # No comment → key omitted (not an empty string).
    assert "comment" not in by_name["Org"]


def test_graph_view_classifies_property_kinds() -> None:
    view = owl_graph_view(_GRAPH_VIEW_TTL)
    by_name = {p["localName"]: p for p in view["properties"]}
    assert by_name["knows"]["kind"] == "object"
    assert by_name["worksAt"]["kind"] == "object"
    assert by_name["name"]["kind"] == "datatype"
    assert by_name["note"]["kind"] == "annotation"


def test_graph_view_object_property_domain_range_are_class_iris() -> None:
    view = owl_graph_view(_GRAPH_VIEW_TTL)
    works = next(p for p in view["properties"] if p["localName"] == "worksAt")
    assert works["domain"] == ["http://example.org/Person"]
    assert works["range"] == ["http://example.org/Org"]


@pytest.mark.parametrize("empty", [None, "", "   ", "\n\t"])
def test_graph_view_empty_input_yields_empty_lists(empty: Any) -> None:
    assert owl_graph_view(empty) == {"classes": [], "properties": []}


def test_graph_view_malformed_turtle_raises_owl_parse_error() -> None:
    with pytest.raises(OwlParseError) as excinfo:
        owl_graph_view("this is not turtle :{(")
    assert excinfo.value.code == "E_OWL_PARSE"


def test_graph_view_respects_triple_cap() -> None:
    with pytest.raises(OwlBombError) as excinfo:
        owl_graph_view(_GRAPH_VIEW_TTL, max_triples=1)
    assert excinfo.value.code == "E_OWL_TOO_LARGE"


def test_graph_view_property_typed_twice_emits_once_object_wins() -> None:
    """A resource typed as both ObjectProperty and DatatypeProperty (legal
    but unusual RDF) must appear exactly once, under the object kind."""
    ttl = """
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix ex: <http://example.org/> .
    ex:rel a owl:ObjectProperty, owl:DatatypeProperty .
    """
    props = owl_graph_view(ttl)["properties"]
    rel = [p for p in props if p["localName"] == "rel"]
    assert len(rel) == 1
    assert rel[0]["kind"] == "object"


# ---------------------------------------------------------------------------
# Format dispatch — Turtle / RDF-XML / JSON-LD / N-Triples (04-02 Task 1)
# ---------------------------------------------------------------------------


def _pg_graph() -> Graph:
    g = Graph()
    g.parse(data=PG_TURTLE, format="turtle")
    return g


PG_RDFXML = _pg_graph().serialize(format="xml")
PG_JSONLD = _pg_graph().serialize(format="json-ld")
PG_NTRIPLES = _pg_graph().serialize(format="nt")


def test_turtle_to_mapping_rdfxml_roundtrip_parity() -> None:
    """RDF/XML import must yield the same entity/relationship surface
    as the Turtle import of the same ontology (D-04 roundtrip parity)."""

    turtle_bundle = turtle_to_mapping(PG_TURTLE)
    xml_bundle = turtle_to_mapping(PG_RDFXML, format="xml")
    assert xml_bundle.entities() == turtle_bundle.entities()
    assert xml_bundle.relationships() == turtle_bundle.relationships()


def test_turtle_to_mapping_rdfxml_accepts_mime_string() -> None:
    """``format=`` also accepts a bare MIME type, not just the rdflib name."""

    bundle = turtle_to_mapping(PG_RDFXML, format="application/rdf+xml")
    assert set(bundle.entities()) == {"Person", "Org"}


def test_turtle_to_mapping_json_ld_roundtrip() -> None:
    bundle = turtle_to_mapping(PG_JSONLD, format="json-ld")
    assert set(bundle.entities()) == {"Person", "Org"}
    assert set(bundle.relationships()) == {"knows", "worksAt"}


def test_turtle_to_mapping_ntriples_roundtrip() -> None:
    bundle = turtle_to_mapping(PG_NTRIPLES, format="nt")
    assert set(bundle.entities()) == {"Person", "Org"}
    assert set(bundle.relationships()) == {"knows", "worksAt"}


def test_mapping_to_turtle_xml_output_is_isomorphic_to_turtle() -> None:
    """``mapping_to_turtle(bundle, format="xml")`` output must re-parse
    under rdflib ``format="xml"`` and be isomorphic to the Turtle
    serialisation of the same bundle."""

    bundle = turtle_to_mapping(PG_TURTLE, preserve_owl=False)
    turtle_out = mapping_to_turtle(bundle)
    xml_out = mapping_to_turtle(bundle, format="xml")

    g_turtle = Graph()
    g_turtle.parse(data=turtle_out, format="turtle")
    g_xml = Graph()
    g_xml.parse(data=xml_out, format="xml")
    assert g_turtle.isomorphic(g_xml)


def test_mapping_to_turtle_xml_from_inline_owl_turtle_reserialises() -> None:
    """When the bundle carries an inline ``owl_turtle`` (the common
    case), requesting ``format="xml"`` must re-serialise rather than
    return the Turtle verbatim."""

    bundle = turtle_to_mapping(PG_TURTLE)  # preserve_owl defaults True
    xml_out = mapping_to_turtle(bundle, format="xml")
    assert xml_out != bundle.owl_turtle
    g = Graph()
    g.parse(data=xml_out, format="xml")
    assert len(g) == len(_pg_graph())


def test_mapping_to_turtle_json_ld_and_nt_round_trip_same_bundle() -> None:
    bundle = turtle_to_mapping(PG_TURTLE, preserve_owl=False)
    jsonld_out = mapping_to_turtle(bundle, format="json-ld")
    nt_out = mapping_to_turtle(bundle, format="nt")

    g_jsonld = Graph()
    g_jsonld.parse(data=jsonld_out, format="json-ld")
    g_nt = Graph()
    g_nt.parse(data=nt_out, format="nt")
    assert g_jsonld.isomorphic(g_nt)


def test_turtle_to_mapping_preserves_owl_turtle_as_turtle_even_for_xml_import() -> None:
    """``MappingBundle.owl_turtle`` is documented (resolver.py, schema
    routes) as always being Turtle text; importing via ``format="xml"``
    must not leak raw RDF/XML into that slot."""

    bundle = turtle_to_mapping(PG_RDFXML, format="xml")
    assert bundle.owl_turtle is not None
    assert "<?xml" not in bundle.owl_turtle
    g = Graph()
    g.parse(data=bundle.owl_turtle, format="turtle")
    assert g.isomorphic(_pg_graph())


def test_unknown_format_raises_owl_parse_error() -> None:
    with pytest.raises(OwlParseError) as exc_info:
        turtle_to_mapping(PG_TURTLE, format="not-a-real-format")
    assert exc_info.value.code == "E_OWL_PARSE"


def test_unknown_format_on_export_raises_owl_parse_error() -> None:
    bundle = turtle_to_mapping(PG_TURTLE)
    with pytest.raises(OwlParseError) as exc_info:
        mapping_to_turtle(bundle, format="not-a-real-format")
    assert exc_info.value.code == "E_OWL_PARSE"


def test_triple_cap_fires_regardless_of_import_format() -> None:
    """The OWL-bomb triple cap must fire identically whether the input
    was Turtle or RDF/XML — it is applied to the parsed ``Graph``, not
    the input bytes."""

    actual_triples = count_triples(_pg_graph())
    cap = max(1, actual_triples - 1)
    with pytest.raises(OwlBombError) as exc_info:
        turtle_to_mapping(PG_RDFXML, format="xml", max_triples=cap)
    assert exc_info.value.code == "E_OWL_TOO_LARGE"


def test_format_from_mime_resolves_known_types() -> None:
    assert format_from_mime("text/turtle") == "turtle"
    assert format_from_mime("application/rdf+xml") == "xml"
    assert format_from_mime("application/ld+json") == "json-ld"
    assert format_from_mime("application/n-triples") == "nt"


def test_format_from_mime_unknown_returns_none() -> None:
    assert format_from_mime("application/json") is None
    assert format_from_mime("") is None
    assert format_from_mime(None) is None


# ---------------------------------------------------------------------------
# RDF/XML pre-parse DOCTYPE/ENTITY guard (billion-laughs / XXE — 04-02 Task 3)
# ---------------------------------------------------------------------------


_XML_BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:ex="http://ex.org/">
  <owl:Class rdf:about="http://ex.org/Person">
    <rdf:comment>&lol3;</rdf:comment>
  </owl:Class>
</rdf:RDF>
"""

_XML_XXE = """<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#">
  <owl:Class rdf:about="http://ex.org/Person">
    <rdf:comment>&xxe;</rdf:comment>
  </owl:Class>
</rdf:RDF>
"""


def test_billion_laughs_rdfxml_raises_owl_parse_error() -> None:
    with pytest.raises(OwlParseError) as exc_info:
        turtle_to_mapping(_XML_BILLION_LAUGHS, format="xml")
    assert exc_info.value.code == "E_OWL_PARSE"


def test_external_entity_rdfxml_raises_owl_parse_error() -> None:
    with pytest.raises(OwlParseError) as exc_info:
        turtle_to_mapping(_XML_XXE, format="xml")
    assert exc_info.value.code == "E_OWL_PARSE"


def test_dtd_free_rdfxml_still_parses_successfully() -> None:
    """The guard must not reject legitimate, DOCTYPE-free RDF/XML."""

    bundle = turtle_to_mapping(PG_RDFXML, format="xml")
    assert set(bundle.entities()) == {"Person", "Org"}


def test_parse_owl_graph_applies_dtd_guard_for_xml_format() -> None:
    with pytest.raises(OwlParseError):
        parse_owl_graph(_XML_BILLION_LAUGHS, "xml")


def test_parse_owl_graph_does_not_guard_non_xml_formats() -> None:
    """The DOCTYPE/ENTITY guard is RDF/XML-specific — Turtle input is
    never scanned for it."""

    graph = parse_owl_graph(PG_TURTLE, "turtle")
    assert len(graph) == len(_pg_graph())
