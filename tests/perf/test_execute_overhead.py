"""CI-gated p95 latency gate for ``POST /execute`` overhead.

Delivers the third D-08 CI-blocking perf row (PRD §9.4): translate +
dispatch overhead, EXPLICITLY EXCLUDING AQL execution time. The only
real I/O ``/execute`` performs is ``session.db.aql.execute(...)``
(``arango_sparql/service/routes/sparql.py``) — this file monkeypatches
``arango_sparql.service.ArangoClient`` to the proven
``_FakeArangoClient``/``_FakeDb``/``_FakeCursor`` double (re-exported
from :mod:`tests.perf.conftest`, single source of truth in
``tests.test_service_sparql_routes``) so that call returns an instant
fake cursor. Without this stub the row would silently become
Docker-dependent (04-RESEARCH.md Pitfall 2) — stubbing it is correct
because the row is *defined* as translate+dispatch excluding AQL exec,
not a workaround.

Percentiles use the stdlib ``statistics.quantiles`` helper (``p95``,
re-exported from :mod:`tests.perf.conftest`) — no ``pytest-benchmark``,
no ``numpy``/``scipy``.

**Environment-matched gating:** the hard ``p95 <= baseline * 1.25``
assertion only fires when the current run's environment
(``"ci"`` if ``CI`` is set, else ``"local"``) matches the checked-in
``baseline.json``'s ``captured_env``. On a mismatch (or a missing
baseline row) the test emits a ``warnings.warn`` with both numbers and
passes — advisory only.
"""

from __future__ import annotations

import contextlib
import gc
import logging
import os
import time
import warnings

import pytest
from fastapi.testclient import TestClient

import arango_sparql.service as svc
from arango_sparql.service import app
from arango_sparql.service.security import _TokenBucket
from tests.perf.conftest import _connect_session, load_baseline, p95

pytestmark = pytest.mark.perf

# N=120, discard first 20 as warmup -> 100 samples feed statistics.quantiles.
_N_ITER = 120
_WARMUP = 20

# Minimal ontology mapping :Thing to a collection so the resolver can
# translate the ASK query below without a W_SCHEMA_DEFAULT_COLLECTION
# fallback warning muddying the row.
_ONTOLOGY_TTL = """
@prefix : <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .

:Thing a owl:Class ;
    phys:collectionName "Thing" .
"""

# AQL for the execute row is pinned to a trivial, always-cheap query
# ("ASK is essentially SELECT LIMIT 1" per tests/translate/ask.yml) so
# the fake cursor's instant return dominates — the row measures
# translate+dispatch overhead, not AQL execution time.
_ASK_QUERY = "PREFIX : <http://ex.org/> ASK { ?s a :Thing }"


@contextlib.contextmanager
def _quiet_logging():
    """Suppress logging + defer GC for the duration of a measurement loop.

    ``execute_endpoint`` emits one ``logger.info`` per request
    (``log_endpoint_timing``); under pytest's captured-stdout
    redirection this I/O cost is uneven enough to occasionally land in
    the p95 bucket and destabilize the gate with jitter unrelated to
    the measured translate+dispatch work. A mid-loop GC pass is the
    other common source of a single-iteration outlier (T-04-12
    mitigation: a stable central value, not GC/I/O noise) --
    ``gc.collect()`` runs once up front so the loop starts from a
    clean generation, then ``gc.disable()`` keeps a cyclic-collector
    pass from landing inside the timed window.
    """
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        gc.enable()
        logging.disable(previous)


def _current_env() -> str:
    return "ci" if os.environ.get("CI") else "local"


def _gate(row_key: str, measured_p95_ms: float) -> None:
    """Enforce (or advise on) the ``* 1.25`` p95 budget for *row_key*.

    Enforced only when the current run environment matches the
    checked-in baseline's ``captured_env``; advisory (warn + pass)
    otherwise, and skipped entirely when the baseline row is absent
    (first capture run, before ``baseline.json`` has this key).
    """
    baseline = load_baseline()
    budget = baseline.get("rows", {}).get(row_key)
    if budget is None:
        pytest.skip(f"no checked-in baseline row {row_key!r} yet (first capture run)")
        return

    current_env = _current_env()
    captured_env = baseline.get("captured_env")
    tolerated = budget * 1.25
    if current_env == captured_env:
        assert measured_p95_ms <= tolerated, (
            f"{row_key}: p95={measured_p95_ms:.3f}ms exceeds budget "
            f"{tolerated:.3f}ms (baseline={budget}ms, env={captured_env!r})"
        )
    else:
        warnings.warn(
            f"{row_key}: baseline captured_env={captured_env!r} does not match "
            f"current run env {current_env!r} -- advisory only (gate not "
            f"enforced). measured p95={measured_p95_ms:.3f}ms, baseline="
            f"{budget}ms (*1.25={tolerated:.3f}ms)",
            stacklevel=2,
        )


def test_execute_overhead_p95(monkeypatch: pytest.MonkeyPatch, fake_client_factory: type) -> None:
    # fake_client_factory (session-scoped fixture from tests.perf.conftest,
    # itself re-exported from tests.test_service_sparql_routes) already
    # monkeypatches svc.ArangoClient -- /connect never touches a real DB.
    monkeypatch.setattr(svc, "_compute_bucket", _TokenBucket(10_000))
    # /execute's analyzer-enrichment path (_analyzer_bundle_for_session ->
    # _get_or_acquire, strategy="auto") resolves an LLM provider from
    # OPENAI_API_KEY/ANTHROPIC_API_KEY/OPENROUTER_API_KEY/LLM_PROVIDER/
    # SCHEMA_ANALYZER_PROVIDER when arangodb-schema-analyzer is installed
    # (verified this session: a repo-local .env sets OPENAI_API_KEY, which
    # this route layer picks up via _resolve_analyzer_provider). It fails
    # fast against our _FakeDb (no .collections()) today and degrades
    # silently, but a CI-gated, Docker/network-free perf row must not
    # depend on that failure ordering never changing -- explicitly force
    # the deterministic-baseline path so this row never risks a live LLM
    # call regardless of the host's ambient env/.env configuration.
    for _var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "LLM_PROVIDER",
        "SCHEMA_ANALYZER_PROVIDER",
    ):
        monkeypatch.delenv(_var, raising=False)
    client = TestClient(app)
    token = _connect_session(client)

    samples: list[float] = []
    with _quiet_logging():
        for _ in range(_N_ITER):
            t0 = time.perf_counter()
            resp = client.post(
                "/execute",
                headers={"Authorization": f"Bearer {token}"},
                json={"sparql": _ASK_QUERY, "ontology_ttl": _ONTOLOGY_TTL},
            )
            samples.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200, resp.text
    measured = p95(samples[_WARMUP:])
    _gate("execute_overhead_p95_ms", measured)
