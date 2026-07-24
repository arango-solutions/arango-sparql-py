"""WR-02: parity gate -- the two adapters' `grounding_prompt_section` must
stay byte-identical forever.

`SparqlLanguageAdapter.grounding_prompt_section` (adapter.py) and
`SparqlAdapter.grounding_prompt_section` (engine_adapter.py) are verbatim-
duplicated implementations; both docstrings explicitly warn "do NOT
paraphrase; rephrasing invalidates the measured lift" (the empirically
measured CK25 +12.2pt lift). Nothing else in the test suite exercises both
adapters side by side (`test_adapter.py` only builds `SparqlLanguageAdapter`,
`test_grounding_engine_prompt.py` only builds `SparqlAdapter`), so a future
edit applied to one file could silently diverge from the other without any
test failing. This test constructs both adapters against the same
`LabelIndex`/question fixture and asserts their rendered
`grounding_prompt_section` outputs are equal.
"""

from __future__ import annotations

import pytest

pytest.importorskip("arango_query_core", reason="nl extra (arango-query-core) required")

from arango_query_core.nl.grounding import GroundedEntity, LabelIndex  # noqa: E402

from arango_sparql.nl2sparql.adapter import SparqlLanguageAdapter  # noqa: E402
from arango_sparql.nl2sparql.engine_adapter import SparqlAdapter  # noqa: E402
from arango_sparql.translate.resolver import SchemaResolver  # noqa: E402

ONTOLOGY_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
<http://example.org/Person> a owl:Class ; phys:collectionName "Person" .
<http://example.org/name> a owl:DatatypeProperty .
""".strip()

_SENTINEL_LABEL = "Sentinel Widget XYZ123"


def _index() -> LabelIndex:
    return LabelIndex.from_items(
        [GroundedEntity(id="http://ex.org/w1", labels=(_SENTINEL_LABEL,), type="Widget")]
    )


def test_grounding_prompt_section_byte_identical_across_adapters() -> None:
    resolver = SchemaResolver.from_turtle(ONTOLOGY_TTL)
    index = _index()
    question = f"find the {_SENTINEL_LABEL}"

    language_adapter = SparqlLanguageAdapter(resolver=resolver, ontology_ttl=ONTOLOGY_TTL)
    engine_adapter = SparqlAdapter(resolver=resolver, ontology_ttl=ONTOLOGY_TTL)

    language_output = language_adapter.grounding_prompt_section(question, index, k=20)
    engine_output = engine_adapter.grounding_prompt_section(question, index, k=20)

    assert language_output == engine_output
    # Sanity: the fixture actually rendered something (not two empty strings
    # that happen to be equal) -- a real retrieval hit for the sentinel.
    assert _SENTINEL_LABEL in language_output
