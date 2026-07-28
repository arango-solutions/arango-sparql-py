"""CI-gated p95 latency gate for ``POST /translate`` — cold vs warm rows.

Delivers two of the three D-08 CI-blocking perf rows (PRD §9.4):

* ``translate_cold_p95_ms`` — a distinct, never-before-seen ontology +
  query is built for every iteration (fresh Turtle parse, fresh
  resolver, fresh SPARQL parse each time — "cold mapping" per §9.4).
* ``translate_warm_p95_ms`` — the exact same ontology + query is reused
  across every iteration (steady-state / repeated-request shape).

Fully in-process: ``/translate`` never touches a database (it works
without a session — see ``translate_endpoint``'s optional session
dependency), so no ``_FakeArangoClient`` double is needed here. Zero
Docker, zero real I/O.

Percentiles use the stdlib ``statistics.quantiles`` helper re-exported
from :mod:`tests.perf.conftest` (``p95``) — no ``pytest-benchmark``, no
``numpy``/``scipy``.

**Environment-matched gating:** the hard ``p95 <= baseline * 1.25``
assertion only fires when the current run's environment
(``"ci"`` if ``CI`` is set, else ``"local"``) matches the checked-in
``baseline.json``'s ``captured_env``. On a mismatch (or a missing
baseline row, e.g. the very first capture run) the test emits a
``warnings.warn`` with both numbers and passes — advisory only.
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
from tests.perf.conftest import load_baseline, p95

pytestmark = pytest.mark.perf

# N=120, discard first 20 as warmup -> 100 samples feed statistics.quantiles.
# Matches 04-PATTERNS.md's vetted sketch and 04-RESEARCH.md Open Question 3
# (N=100-200, discard first 10-20).
_N_ITER = 120
_WARMUP = 20

# ---------------------------------------------------------------------------
# WARM row fixture data — identical payload reused every iteration.
# ---------------------------------------------------------------------------
_WARM_ONTOLOGY_TTL = """
@prefix : <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Person a owl:Class ;
    phys:collectionName "Person" .

:name a owl:DatatypeProperty ;
    rdfs:domain :Person ;
    rdfs:range <http://www.w3.org/2001/XMLSchema#string> .
"""

_WARM_QUERY = """
PREFIX : <http://ex.org/>
SELECT ?s ?n WHERE {
  ?s a :Person ;
     :name ?n .
}
LIMIT 5
"""


def _cold_ttl(i: int) -> str:
    """Build a never-before-seen ontology for iteration *i*.

    A distinct class/property local name each time forces a genuinely
    fresh Turtle parse + resolver build every call — the "cold mapping"
    row measures a schema the process has never resolved before,
    as opposed to the warm row's steady-state repeat.
    """
    return f"""
@prefix : <http://ex.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix phys: <https://arango.solutions/phys#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Person{i} a owl:Class ;
    phys:collectionName "Person" .

:name{i} a owl:DatatypeProperty ;
    rdfs:domain :Person{i} ;
    rdfs:range <http://www.w3.org/2001/XMLSchema#string> .
"""


def _cold_query(i: int) -> str:
    return f"""
PREFIX : <http://ex.org/>
SELECT ?s ?n WHERE {{
  ?s a :Person{i} ;
     :name{i} ?n .
}}
LIMIT 5
"""


@contextlib.contextmanager
def _quiet_logging():
    """Suppress logging + defer GC for the duration of a measurement loop.

    ``translate_endpoint`` emits one ``logger.info`` per request
    (``log_endpoint_timing``); under pytest's captured-stdout
    redirection this I/O cost is uneven enough to occasionally land in
    the p95 bucket and destabilize the gate with jitter unrelated to
    the measured translate work. A mid-loop GC pass is the other
    common source of a single-iteration outlier (T-04-12 mitigation:
    a stable central value, not GC/I/O noise) -- ``gc.collect()`` runs
    once up front so the loop starts from a clean generation, then
    ``gc.disable()`` keeps a cyclic-collector pass from landing inside
    the timed window.
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


def test_translate_cold_p95(monkeypatch: pytest.MonkeyPatch) -> None:
    # A high-capacity bucket keeps this loop deterministic regardless of
    # the default COMPUTE_RATE_LIMIT_PER_MINUTE=100 (established pattern:
    # tests/test_service_nl_routes.py's _reset_rate_limits fixture).
    monkeypatch.setattr(svc, "_compute_bucket", _TokenBucket(10_000))
    client = TestClient(app)
    samples: list[float] = []
    with _quiet_logging():
        for i in range(_N_ITER):
            ttl = _cold_ttl(i)
            query = _cold_query(i)
            t0 = time.perf_counter()
            resp = client.post("/translate", json={"sparql": query, "ontology_ttl": ttl})
            samples.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200, resp.text
    measured = p95(samples[_WARMUP:])
    _gate("translate_cold_p95_ms", measured)


def test_translate_warm_p95(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_compute_bucket", _TokenBucket(10_000))
    client = TestClient(app)
    samples: list[float] = []
    with _quiet_logging():
        for _ in range(_N_ITER):
            t0 = time.perf_counter()
            resp = client.post(
                "/translate",
                json={"sparql": _WARM_QUERY, "ontology_ttl": _WARM_ONTOLOGY_TTL},
            )
            samples.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200, resp.text
    measured = p95(samples[_WARMUP:])
    _gate("translate_warm_p95_ms", measured)
