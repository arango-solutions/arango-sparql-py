"""Report-only memory-ceiling row (under concurrent load) — PRD §9.4
(D-09).

PRD §9.4 row: **Memory ceiling, 100 concurrent `/execute`, 10k-row
payloads** — target p95 ≤ 1.5 GiB RSS, Report-only tier.

**Concurrency scaled down from the PRD's illustrative "100" (documented
deviation, D-09 permits it):** this suite runs against a single
``docker-compose`` ArangoDB container sized for a laptop/CI-runner
sandbox, not a production cluster; 100 truly concurrent 10k-row
``/execute`` calls would risk starving that container rather than
measuring this service's own memory ceiling. ``_N_CONCURRENT`` below
is a fraction of the PRD's number — the row still measures a genuine
concurrent-load RSS peak against the full 10k-row payload the budget
names (``_MAX_RESULT_DOCS`` in ``arango_sparql/service/models.py``),
it is just directionally, not literally, at "100 concurrent" (report-
only rows are advisory by design, D-09 — see PLAN.md's
``must_haves.truths``).

Gated behind ``RUN_INTEGRATION=1`` + a real ``docker-compose``
ArangoDB, mirroring every other Docker-dependent report row.

Same MiB-into-a-ms-shaped-appender unit note as
``test_memory_idle.py``: ``append_report``'s column header literally
reads "p95 (ms)"; the row name's ``_rss_mib_p95`` suffix disambiguates
for a human reviewer.
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

_TEST_COLLECTION = "PerfMemoryLoadPerson"
_ROW_COUNT = 10_000  # PRD §9.4's "10k-row payloads" (== _MAX_RESULT_DOCS)
_N_CONCURRENT = 10  # scaled down from the PRD's illustrative 100 -- see module docstring
_N_ROUNDS = 3  # p95() needs >= 2 points; ru_maxrss is a monotonic peak.
_BUDGET_MIB = 1536.0  # 1.5 GiB

_ONTOLOGY_TTL = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix :     <http://example.org/perf-memload#> .

:PerfMemoryLoadPerson a owl:Class ;
    phys:collectionName "PerfMemoryLoadPerson" .

:name a owl:DatatypeProperty ;
    rdfs:domain :PerfMemoryLoadPerson ;
    rdfs:range  xsd:string .
"""

_SELECT_QUERY = (
    "PREFIX : <http://example.org/perf-memload#> SELECT ?s ?n WHERE { ?s a :PerfMemoryLoadPerson ; :name ?n }"
)


def _rss_mib() -> float:
    import resource
    import sys

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024


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
def _seeded_collection(_live_arango: None) -> Iterator[int]:
    """Drop-and-recreate a ``PerfMemoryLoadPerson`` collection seeded
    with ``_ROW_COUNT`` rows — the "10k-row payloads" PRD §9.4 calls
    for on this row."""

    from arango import ArangoClient

    client = ArangoClient(hosts=DEFAULT_ARANGO_URL)
    db = client.db(DEFAULT_ARANGO_DB, username=DEFAULT_ARANGO_USER, password=DEFAULT_ARANGO_PASSWORD)

    if db.has_collection(_TEST_COLLECTION):
        db.delete_collection(_TEST_COLLECTION)
    coll = db.create_collection(_TEST_COLLECTION)

    docs = [
        {"_uri": f"http://example.org/perf-memload#p{i}", "name": f"Person{i}"} for i in range(_ROW_COUNT)
    ]
    coll.insert_many(docs)

    try:
        yield _ROW_COUNT
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


def test_memory_load_rss_p95(monkeypatch: pytest.MonkeyPatch, _seeded_collection: int) -> None:
    """Report-only RSS row under ``_N_CONCURRENT`` concurrent
    ``/execute`` calls against the seeded 10k-row collection, repeated
    ``_N_ROUNDS`` times so ``ru_maxrss``'s peak-so-far semantics still
    yield >= 2 distinct samples for :func:`p95`. Never asserts against
    the §9.4 budget (D-09) — only appends the measured MiB figure to
    ``LATENCY_REPORT.md``.
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

    def _one_execute() -> int:
        resp = client.post(
            "/execute",
            headers=headers,
            json={"sparql": _SELECT_QUERY, "ontology_ttl": _ONTOLOGY_TTL},
        )
        assert resp.status_code == 200, resp.text
        return len(resp.json()["bindings"])

    samples: list[float] = []
    for _ in range(_N_ROUNDS):
        with ThreadPoolExecutor(max_workers=_N_CONCURRENT) as pool:
            row_counts = list(pool.map(lambda _i: _one_execute(), range(_N_CONCURRENT)))
        assert all(count == _ROW_COUNT for count in row_counts), row_counts
        samples.append(_rss_mib())
        time.sleep(0.05)

    measured = p95(samples)
    append_report("memory_load_rss_mib_p95", measured, _BUDGET_MIB)
