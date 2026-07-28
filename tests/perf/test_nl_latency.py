"""Report-only p95 latency row for ``POST /nl-translate`` — PRD §9.4
(D-09), the **live-LLM** row.

PRD §9.4 row: **`/nl-translate` (single LLM round-trip, no repair)** —
target p95 ≤ 3.5s, SLO p99 ≤ 8s, measured against ``gpt-4o-mini``,
Report-only tier.

**Key gating (T-04-13, never-commit-a-secret):** mirrors the
``NL2SPARQL_API_KEY``-gated live sweep convention already established
by ``tests/nl2sparql/eval/README.md`` §3 (Pitfall 1 there: the live
path reads ``NL2SPARQL_API_KEY``, *not* ``OPENAI_API_KEY``). This
module-level ``skipif`` means the suite skips cleanly key-free — the
default state for CI and for this agent's own sandbox — and the key
itself is never read into a variable that could leak into an
assertion message, a log line, or this file. No Docker dependency:
``/nl-translate`` never touches a database.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from tests.perf.conftest import append_report, p95

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(
        not os.environ.get("NL2SPARQL_API_KEY"),
        reason="set NL2SPARQL_API_KEY (never OPENAI_API_KEY) to run the live /nl-translate report row",
    ),
]

# A live LLM round-trip costs real seconds and real cents per call —
# far fewer samples than the in-process rows' N=100-200. Enough for an
# advisory p95 estimate (D-09), not a statistically powered gate.
_N_ITER = 5
_WARMUP = 1
_BUDGET_MS = 3500.0

_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/perf-nl#> .

:Person a owl:Class ;
    phys:collectionName "Person" .

:name a owl:DatatypeProperty ;
    rdfs:domain :Person ;
    rdfs:range  xsd:string .
"""

_NL_QUESTION = "What are the names of all people?"


def test_nl_translate_p95(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report-only p95 for a single-shot (``max_repairs=0``) live
    ``/nl-translate`` call. Never asserts against the §9.4 budget
    (D-09) — only appends the measured number to
    ``LATENCY_REPORT.md``. A translation failure (422) still yields a
    valid latency sample; only a hard transport error is a bug.
    """

    import arango_sparql.service as svc
    from arango_sparql.service import app
    from arango_sparql.service.security import _TokenBucket

    # A high-capacity bucket keeps the loop deterministic regardless
    # of the default NL_RATE_LIMIT_PER_MINUTE (established pattern:
    # tests/test_service_nl_routes.py's _reset_rate_limits fixture).
    monkeypatch.setattr(svc, "_nl_bucket", _TokenBucket(10_000))

    client = TestClient(app)
    samples: list[float] = []
    for _ in range(_N_ITER):
        t0 = time.perf_counter()
        resp = client.post(
            "/nl-translate",
            json={
                "nl": _NL_QUESTION,
                "ontology_ttl": _ONTOLOGY_TTL,
                "max_repairs": 0,
            },
        )
        samples.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code in (200, 422), resp.text

    measured = p95(samples[_WARMUP:])
    append_report("nl_translate_p95_ms", measured, _BUDGET_MS)
