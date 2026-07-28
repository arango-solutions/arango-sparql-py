"""Report-only concurrency row for concurrent ``POST /execute`` — PRD
§9.4 (D-09).

PRD §9.4 row: **Concurrency ceiling** (no error budget burn at 100
concurrent ``/execute`` against pinned AQL) — target ``n/a`` p50/p95,
SLO ``>= 100 concurrent``, Report-only tier.

**Concurrency scaled down from the PRD's illustrative "100"** — same
documented deviation as ``test_memory_load.py``: this suite targets a
single sandboxed ``docker-compose`` ArangoDB container, not a
production cluster. ``_N_CONCURRENT`` below still exercises genuine
concurrent dispatch against a pinned, cheap AQL query (mirrors
``test_execute_overhead.py``'s "AQL pinned to a trivial query" idea,
here against a *real* ArangoDB rather than the fake double); the row
still reports two useful numbers: the concurrent-call p95 latency and
whether any request burned the "no error budget" invariant the PRD
row actually gates on (asserted directly — this is a correctness
check, not a §9.4 budget assertion, so it is not itself a Rule
violation of D-09's "advisory only" framing).

Gated behind ``RUN_INTEGRATION=1`` + a real ``docker-compose``
ArangoDB, mirroring every other Docker-dependent report row.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.integration.conftest import (
    DEFAULT_ARANGO_DB,
    DEFAULT_ARANGO_PASSWORD,
    DEFAULT_ARANGO_URL,
    DEFAULT_ARANGO_USER,
    arangodb_reachable,
    ensure_test_database,
    integration_enabled,
    try_boot_arangodb_via_compose,
)
from tests.perf.conftest import append_report, p95

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

# Pinned, cheap AQL-equivalent query -- mirrors test_execute_overhead.py's
# "ASK is essentially SELECT LIMIT 1" reasoning, here against a real
# ArangoDB rather than the fake double.
_ASK_QUERY = "PREFIX : <http://example.org/perf-concurrency#> ASK { ?s a :PerfConcurrencyThing }"


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped Docker gate, mirroring every ``tests/integration/*``
    file's fixture of the same name."""

    if not integration_enabled():
        pytest.skip("set RUN_INTEGRATION=1 to enable the Docker-gated perf report rows")
    if not arangodb_reachable():
        if not try_boot_arangodb_via_compose():
            pytest.skip(f"ArangoDB at {DEFAULT_ARANGO_URL} is unreachable and could not be booted")
    ensure_test_database()
    yield


@pytest.fixture(scope="module")
def _seeded_collection(_live_arango: None) -> Iterator[list[dict]]:
    """Drop-and-recreate a small ``PerfConcurrencyPerson`` collection
    so the pinned ``ASK`` has a real (cheap) collection to resolve
    against."""

    from arango import ArangoClient

    client = ArangoClient(hosts=DEFAULT_ARANGO_URL)
    db = client.db(DEFAULT_ARANGO_DB, username=DEFAULT_ARANGO_USER, password=DEFAULT_ARANGO_PASSWORD)

    if db.has_collection(_TEST_COLLECTION):
        db.delete_collection(_TEST_COLLECTION)
    coll = db.create_collection(_TEST_COLLECTION)

    docs = [{"_uri": "http://example.org/perf-concurrency#k1"}]
    coll.insert_many(docs)

    try:
        yield docs
    finally:
        try:
            db.delete_collection(_TEST_COLLECTION)
        except Exception:
            # Best-effort teardown — a failed delete shouldn't mask a
            # real test failure upstream.
            pass
        client.close()


def _connect_session(client) -> str:
    resp = client.post(
        "/connect",
        json={
            "url": DEFAULT_ARANGO_URL,
            "database": DEFAULT_ARANGO_DB,
            "username": DEFAULT_ARANGO_USER,
            "password": DEFAULT_ARANGO_PASSWORD,
        },
    )
    assert resp.status_code == 200, f"connect failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


def test_concurrency_p95_no_error_budget_burn(
    monkeypatch: pytest.MonkeyPatch, _seeded_collection: list[dict]
) -> None:
    """Report-only p95 latency for ``_N_CONCURRENT`` concurrent
    ``/execute`` calls against the pinned ``ASK`` query. Asserts the
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
    token = _connect_session(client)

    bundle = turtle_to_mapping(_ONTOLOGY_TTL)
    _resolve_schema_cache().put(DEFAULT_ARANGO_DB, bundle)

    headers = {"Authorization": f"Bearer {token}"}

    def _one_execute() -> tuple[int, float]:
        t0 = time.perf_counter()
        resp = client.post(
            "/execute",
            headers=headers,
            json={"sparql": _ASK_QUERY, "ontology_ttl": _ONTOLOGY_TTL},
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
