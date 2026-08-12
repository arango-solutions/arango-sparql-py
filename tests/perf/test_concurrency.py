"""Report-only concurrency row for concurrent ``POST /execute`` — PRD
§9.4 (D-09).

PRD §9.4 row: **Concurrency ceiling** (no error budget burn at 100
concurrent ``/execute`` against pinned AQL) — target ``n/a`` p50/p95,
SLO ``>= 100 concurrent``, Report-only tier.

**Concurrency scaled down from the PRD's illustrative "100"** — same
documented deviation as ``test_memory_load.py``: this suite targets a
single sandboxed ``docker-compose`` ArangoDB container, not a
production cluster. ``_N_CONCURRENT`` below still exercises genuine
concurrent dispatch against a pinned, cheap AQL query; the row still
reports two useful numbers: the concurrent-call p95 latency and
whether any request burned the "no error budget" invariant the PRD
row actually gates on (asserted directly — this is a correctness
check, not a §9.4 budget assertion, so it is not itself a Rule
violation of D-09's "advisory only" framing).

**Pinned query is a SELECT, not ASK (04-07-PLAN.md hardening fix):**
an earlier revision pinned an ``ASK`` query here (mirroring
``test_execute_overhead.py``'s "ASK is essentially SELECT LIMIT 1"
comment) — that reasoning holds against ``test_execute_overhead.py``'s
*fake* ArangoDB double (which returns a fixed dict row regardless of
the AQL sent), but not against a *real* ArangoDB: ``tests/translate/
ask.yml`` documents that ASK genuinely translates to
``RETURN LENGTH(...) > 0``, a scalar boolean cursor result, which
``/execute``'s ``SparqlExecuteResponse.bindings: list[dict]`` contract
cannot represent (a real, previously-uncaught gap this Docker-gated
row was the first test in the suite to exercise). A pinned ``SELECT``
— the same shape every other Docker-gated report row in this suite
already uses successfully — measures genuine concurrent-dispatch
latency without depending on that unrelated, out-of-scope contract
gap; see 04-07-SUMMARY.md's "Known Gaps" for the deferred ``/execute``
ASK-handling fix.

Gated behind ``RUN_INTEGRATION=1`` + a real ``docker-compose``
ArangoDB, mirroring every other Docker-dependent report row.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.perf.conftest import (
    DEFAULT_ARANGO_DB,
    append_report,
    arango_seeded_collection,
    connect_session_or_skip,
    live_arango_or_skip,
    p95,
)

pytestmark = pytest.mark.perf

_TEST_COLLECTION = "PerfConcurrencyPerson"
_N_CONCURRENT = 20  # scaled down from the PRD's illustrative 100 -- see module docstring

_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/perf-concurrency#> .

:PerfConcurrencyThing a owl:Class ;
    phys:collectionName "PerfConcurrencyPerson" .
"""

# Pinned, cheap SELECT query against the real ArangoDB -- see module
# docstring for why this is a SELECT, not an ASK.
_SELECT_QUERY = (
    "PREFIX : <http://example.org/perf-concurrency#> SELECT ?s WHERE { ?s a :PerfConcurrencyThing }"
)


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped Docker + connect/auth gate — see
    ``tests/perf/conftest.py``'s :func:`live_arango_or_skip` (never
    ERRORs on a connect/auth failure; skip-gates instead)."""

    live_arango_or_skip()
    yield


@pytest.fixture(scope="module")
def _seeded_collection(_live_arango: None) -> Iterator[list[dict]]:
    """Drop-and-recreate a small ``PerfConcurrencyPerson`` collection
    so the pinned ``SELECT`` has a real (cheap) collection to resolve
    against."""

    docs = [{"_uri": "http://example.org/perf-concurrency#k1"}]
    with arango_seeded_collection(_TEST_COLLECTION, docs) as seeded:
        yield seeded


def test_concurrency_p95_no_error_budget_burn(
    monkeypatch: pytest.MonkeyPatch, _seeded_collection: list[dict]
) -> None:
    """Report-only p95 latency for ``_N_CONCURRENT`` concurrent
    ``/execute`` calls against the pinned ``SELECT`` query. Asserts the
    PRD row's own "no error budget burn" invariant directly (every
    concurrent call must succeed) but never gates on the measured p95
    itself (D-09) — that figure is appended to ``LATENCY_REPORT.md``
    with ``budget=None`` (report-only, no CI-blocking threshold).
    """

    from fastapi.testclient import TestClient

    import arango_sparql.service as svc
    from arango_sparql.service import app
    from arango_sparql.service.routes.schema import _resolve_schema_cache
    from arango_sparql.service.security import _TokenBucket
    from arango_sparql.translate.owl import turtle_to_mapping

    monkeypatch.setattr(svc, "_compute_bucket", _TokenBucket(10_000))

    client = TestClient(app)
    token = connect_session_or_skip(client)

    bundle = turtle_to_mapping(_ONTOLOGY_TTL)
    _resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)

    headers = {"Authorization": f"Bearer {token}"}

    def _one_execute() -> tuple[int, float]:
        t0 = time.perf_counter()
        resp = client.post(
            "/execute",
            headers=headers,
            json={"sparql": _SELECT_QUERY, "ontology_ttl": _ONTOLOGY_TTL},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        return resp.status_code, elapsed

    with ThreadPoolExecutor(max_workers=_N_CONCURRENT) as pool:
        results = list(pool.map(lambda _i: _one_execute(), range(_N_CONCURRENT)))

    statuses = [status for status, _elapsed in results]
    assert all(status == 200 for status in statuses), statuses  # no error budget burn (PRD §9.4 row)

    samples = [elapsed for _status, elapsed in results]
    measured = p95(samples)
    append_report("concurrency_p95_ms", measured, None)
