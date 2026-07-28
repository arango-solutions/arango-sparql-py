"""Report-only p95 latency rows for ``GET /schema/introspect`` — PRD
§9.4 (D-09).

Two of the 8 Docker/LLM/noisy §9.4 rows measured here, both
report-only (never CI-gating, D-09):

* ``schema_introspect_cache_miss_p95_ms`` — ``force=true`` on every
  call, forcing a fresh :func:`acquire_mapping_bundle` each time
  (PRD §9.4: "analyzer-backed, cache miss, ≤ 1k collections", target
  p95 ≤ 2.5s).
* ``schema_introspect_cache_hit_p95_ms`` — ``force=false`` after one
  warming call, hitting the process-wide ``SchemaCache`` (target
  p95 ≤ 15ms).

Gated behind ``RUN_INTEGRATION=1`` + a real ``docker-compose``
ArangoDB, mirroring every file under ``tests/integration/`` (boot/skip
helpers imported, not re-copied, from :mod:`tests.integration.conftest`).

**LLM-provider env scrub (Rule 2, mirrors ``test_execute_overhead.py``
Plan 06):** ``strategy="auto"`` acquisition tries the analyzer tier
first, and this repo's own ``.env`` sets ``OPENAI_API_KEY`` (verified
this session — ``arangodb-schema-analyzer`` is installed in this
environment). A report-only latency row must not risk a live LLM call
depending on the host's ambient environment, so every
LLM-provider-selecting env var is cleared for the duration of the
test; the analyzer's own heuristic/structural detection still runs
(no key required for that part), so the row still measures the
"analyzer-backed" acquisition path the budget names, just without an
LLM round-trip riding along non-deterministically.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.perf.conftest import (
    arango_seeded_collection,
    append_report,
    connect_session_or_skip,
    live_arango_or_skip,
    p95,
)

pytestmark = pytest.mark.perf

_TEST_COLLECTION = "PerfSchemaIntrospectPerson"
_N_ITER_MISS = 10
_WARMUP_MISS = 2
_BUDGET_MISS_MS = 2500.0

_N_ITER_HIT = 20
_WARMUP_HIT = 4
_BUDGET_HIT_MS = 15.0

_LLM_PROVIDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "LLM_PROVIDER",
    "SCHEMA_ANALYZER_PROVIDER",
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
    """Drop-and-recreate a small seeded collection so schema
    acquisition has real shape/data to introspect."""

    docs = [
        {"_uri": "http://example.org/perf-introspect#p1", "name": "Ivy", "age": 24},
        {"_uri": "http://example.org/perf-introspect#p2", "name": "Jack", "age": 31},
    ]
    with arango_seeded_collection(_TEST_COLLECTION, docs) as seeded:
        yield seeded


def test_schema_introspect_cache_miss_and_hit_p95(
    monkeypatch: pytest.MonkeyPatch, _seeded_collection: list[dict]
) -> None:
    """Two report-only rows in one test (cache-miss then cache-hit) so
    the module-scoped seeded collection and connection are paid for
    once. Neither asserts against its §9.4 budget (D-09) — both only
    append to ``LATENCY_REPORT.md``.
    """

    import arango_sparql.service as svc
    from arango_sparql.service import app
    from arango_sparql.service.security import _TokenBucket

    monkeypatch.setattr(svc, "_compute_bucket", _TokenBucket(10_000))
    for _var in _LLM_PROVIDER_ENV_VARS:
        monkeypatch.delenv(_var, raising=False)

    client = TestClient(app)
    token = connect_session_or_skip(client)
    headers = {"Authorization": f"Bearer {token}"}

    # --- cache-miss row: force=true forces a fresh acquisition every call ---
    miss_samples: list[float] = []
    for _ in range(_N_ITER_MISS):
        resp = client.get("/schema/introspect", params={"force": "true"}, headers=headers)
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["cache_hit"] is False
        miss_samples.append(payload["elapsed_ms"])
    measured_miss = p95(miss_samples[_WARMUP_MISS:])
    append_report("schema_introspect_cache_miss_p95_ms", measured_miss, _BUDGET_MISS_MS)

    # --- cache-hit row: one warming force=false call, then repeat ---
    warm = client.get("/schema/introspect", params={"force": "false"}, headers=headers)
    assert warm.status_code == 200, warm.text

    hit_samples: list[float] = []
    for _ in range(_N_ITER_HIT):
        resp = client.get("/schema/introspect", params={"force": "false"}, headers=headers)
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["cache_hit"] is True
        hit_samples.append(payload["elapsed_ms"])
    measured_hit = p95(hit_samples[_WARMUP_HIT:])
    append_report("schema_introspect_cache_hit_p95_ms", measured_hit, _BUDGET_HIT_MS)
