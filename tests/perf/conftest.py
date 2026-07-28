"""Shared fixtures and stdlib-only helpers for the Phase-4 perf suite.

Design goals (see ``04-01-PLAN.md`` Task 2 and
``04-RESEARCH.md`` Pattern 3 / Pitfall 2):

* The CI-gated perf rows (``/translate`` cold, ``/translate`` warm,
  ``/execute`` overhead) must stay genuinely dependency-free — no Docker,
  no live ArangoDB, no new third-party dependency (no ``pytest-benchmark``,
  no ``numpy``/``scipy``). We re-use the proven
  ``_FakeArangoClient``/``_FakeDb``/``_FakeCursor`` double that already
  drives the real ``/connect`` -> ``/translate`` -> ``/execute`` path in
  :mod:`tests.test_service_sparql_routes` with zero real I/O, rather than
  building a second, perf-specific test double.
* Percentiles are computed with the stdlib ``statistics`` module
  (``statistics.quantiles(samples, n=100)[94]`` for p95), matching this
  repo's existing "no scipy" convention (``tests/nl2sparql/eval/power.py``).
* Baseline comparison and the human-reviewed Markdown report both follow
  the checked-in-``baseline.json`` convention already established by
  ``tests/nl2sparql/eval/baseline.json``.

This module intentionally re-exports (rather than duplicates) the fake
ArangoDB double: importing directly from
``tests.test_service_sparql_routes`` keeps a single source of truth for
the double's behaviour, so a future change there (e.g. a new cursor
field) does not silently drift between the route-contract tests and the
perf suite.
"""

from __future__ import annotations

import contextlib
import json
import os
import statistics
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

import pytest

# --- Pre-empt this repo's dev ``.env`` polluting the Docker-gated
# report rows' ArangoDB target (04-07-PLAN.md hardening fix) ---
#
# The import below (``tests.test_service_sparql_routes``) transitively
# imports ``arango_sparql.service``, whose module-level ``load_dotenv()``
# (see ``arango_sparql/service/app.py``) fills in *any currently-unset*
# ARANGO_* env var from this repo's dev-oriented ``.env`` —
# ``ARANGO_URL=http://localhost:8529`` (this project's own local-dev
# port, NOT the docker-compose test container's host port, 8532 — see
# ``docker-compose.yml``) and ``ARANGO_DB=_system`` (forbidden for
# tests; CLAUDE.md / ``tests/integration/conftest.py`` both mandate
# "never _system"). Because this conftest is always collected before
# any ``tests/perf/test_*.py`` module (pytest loads a directory's
# ``conftest.py`` first), that dotenv call fires *before*
# ``tests/integration/conftest.py`` ever computes its own
# ``DEFAULT_ARANGO_*`` constants — so those constants would otherwise
# silently resolve to the wrong port/database for the whole session.
# ``load_dotenv()`` never overrides an *already-set* var, so locking in
# test-safe defaults here — before the import below can ever trigger
# it — closes that race for good, regardless of collection order.
# Anything a human/CI already exported (``ARANGO_URL``,
# ``ARANGO_TEST_DB``, ``ARANGO_DB``, ...) always wins; these are pure
# no-ops otherwise.
os.environ.setdefault(
    "ARANGO_URL",
    f"http://{os.environ.get('ARANGO_HOST', 'localhost')}:{os.environ.get('ARANGO_PORT', '8532')}",
)
if not (os.environ.get("ARANGO_TEST_DB") or os.environ.get("ARANGO_DB")):
    os.environ["ARANGO_TEST_DB"] = "sparql-to-aql"

# Re-exposed (not duplicated) fake ArangoDB double + connect helper — see
# module docstring above. ``fake_client_factory`` is a ``pytest.fixture``;
# re-exporting it here makes it collectible by any test under
# ``tests/perf/`` without a perf-specific copy of the ~140-line double.
from tests.test_service_sparql_routes import (  # noqa: E402  (after the env-pollution guard above)
    _FakeArangoClient,
    _FakeCursor,
    _FakeDb,
    _connect_session,
    fake_client_factory,
)

# Deferred so the env-pollution guard above always runs first (these
# read/compute ``tests.integration.conftest``'s ``DEFAULT_ARANGO_*``
# module-level constants at import time).
from tests.integration.conftest import (  # noqa: E402
    DEFAULT_ARANGO_DB,
    DEFAULT_ARANGO_PASSWORD,
    DEFAULT_ARANGO_URL,
    DEFAULT_ARANGO_USER,
    arangodb_reachable,
    ensure_test_database,
    integration_enabled,
    try_boot_arangodb_via_compose,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

__all__ = [
    "_FakeArangoClient",
    "_FakeCursor",
    "_FakeDb",
    "_connect_session",
    "fake_client_factory",
    "p95",
    "load_baseline",
    "append_report",
    "live_arango_or_skip",
    "arango_seeded_collection",
    "connect_session_or_skip",
    "connect_session_over_socket_or_skip",
]

# python-arango's connection/auth/forbidden failures all derive from
# ``ArangoError`` (``ArangoClientError`` for local/transport issues,
# ``ArangoServerError``/``DatabaseListError``/etc. for HTTP 401/403/5xx
# responses); ``ConnectionError``/``OSError``/``TimeoutError`` cover the
# raw-socket layer beneath the driver. A report-only perf row (D-09)
# must degrade to a clean skip on any of these — never an ERROR.
from arango.exceptions import ArangoError  # noqa: E402

_DB_CONNECT_ERRORS: tuple[type[Exception], ...] = (
    ArangoError,
    ConnectionError,
    OSError,
    TimeoutError,
)

# Only the three CI-gated rows (D-08) live in ``baseline.json`` — the
# report-only rows (D-09) are recorded solely in ``LATENCY_REPORT.md``.
BASELINE_PATH = Path(__file__).parent / "baseline.json"
LATENCY_REPORT_PATH = Path(__file__).parent / "LATENCY_REPORT.md"


def p95(samples: list[float]) -> float:
    """Return the 95th percentile of ``samples`` (stdlib-only, no numpy/scipy).

    ``statistics.quantiles(samples, n=100)`` returns the 99 inner cut points
    (index 0 = 1st percentile … index 98 = 99th percentile), so the 95th
    percentile is index 94. (The previous ``[93]`` returned the 94th
    percentile, silently under-measuring the CI-gated p95 gates — WR-01.)
    """
    ordered = sorted(samples)
    return statistics.quantiles(ordered, n=100)[94]


def load_baseline() -> dict[str, Any]:
    """Load the checked-in CI-gated perf baseline.

    Returns ``{}`` if ``baseline.json`` does not exist yet so a first-run
    capture (before any baseline has been committed) does not crash.
    """
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text())


def append_report(row_name: str, p95_ms: float, budget_ms: float | None) -> None:
    """Append one Markdown table row to the checked-in latency report.

    ``budget_ms`` is ``None`` for report-only rows (D-09) that have no
    CI-blocking budget — the table still records the measured p95 for
    human review.
    """
    header = "| Row | p95 (ms) | Budget (ms) | Status |\n|---|---|---|---|\n"
    if not LATENCY_REPORT_PATH.exists():
        LATENCY_REPORT_PATH.write_text(
            "# Latency Report\n\n"
            "Checked-in, human-reviewed perf artifact (D-09). Report-only "
            "rows never gate CI; see PRD §9.4 for the full SLO table.\n\n"
            + header
        )
    if budget_ms is None:
        status = "report-only"
    else:
        status = "OK" if p95_ms <= budget_ms else "OVER BUDGET"
    row = f"| {row_name} | {p95_ms:.3f} | {budget_ms if budget_ms is not None else '-'} | {status} |\n"
    with LATENCY_REPORT_PATH.open("a") as fh:
        fh.write(row)


# --- Shared skip-gating helpers for the Docker-dependent report rows ---
#
# Every ``tests/perf/test_*.py`` Docker-gated report row previously
# duplicated its own ``_live_arango`` / ``_seeded_collection`` /
# ``_connect_session`` fixture bodies. Beyond the duplication, the
# duplicated bodies let a genuine ArangoDB connect/auth failure
# propagate as a pytest ERROR — appropriate for the CI-gated
# ``tests/integration/*`` suite (a hard failure signal is exactly what
# that suite wants), but wrong for these report-only rows (D-09): they
# must degrade to a clean ``pytest.skip()`` on any connect/auth
# failure, never an ERROR (04-07-PLAN.md hardening fix). These helpers
# centralize both concerns in one place.


def live_arango_or_skip() -> None:
    """Shared Docker + connect/auth gate for perf report rows.

    Mirrors every ``tests/integration/*`` file's ``_live_arango``
    fixture (``RUN_INTEGRATION`` gate, reachability probe / compose
    boot), but wraps ``ensure_test_database()`` in try/except so any
    ArangoDB connect/auth failure (bad credentials, forbidden
    database, server unreachable after boot, ...) skip-gates instead
    of erroring.
    """
    if not integration_enabled():
        pytest.skip("set RUN_INTEGRATION=1 to enable the Docker-gated perf report rows")
    if not arangodb_reachable():
        if not try_boot_arangodb_via_compose():
            pytest.skip(f"ArangoDB at {DEFAULT_ARANGO_URL} is unreachable and could not be booted")
    try:
        ensure_test_database()
    except _DB_CONNECT_ERRORS as exc:
        pytest.skip(f"ArangoDB connect/auth failed ({exc!r}); skipping report-only row")


@contextlib.contextmanager
def arango_seeded_collection(name: str, docs: list[dict]) -> Iterator[list[dict]]:
    """Drop-and-recreate ``name`` seeded with ``docs``, best-effort
    deleting it again on exit.

    Shared by every Docker-gated report row's ``_seeded_collection``
    fixture. Skip-gates (``pytest.skip``) on any ArangoDB connect/auth
    failure instead of raising — same rationale as
    :func:`live_arango_or_skip`. Callers that need something other
    than the seeded ``docs`` list itself (e.g. ``test_memory_load.py``
    wants the row count) can ignore the yielded value and yield their
    own from within the ``with`` block.
    """
    from arango import ArangoClient

    client: Any = None
    db: Any = None
    try:
        client = ArangoClient(hosts=DEFAULT_ARANGO_URL)
        db = client.db(DEFAULT_ARANGO_DB, username=DEFAULT_ARANGO_USER, password=DEFAULT_ARANGO_PASSWORD)
        if db.has_collection(name):
            db.delete_collection(name)
        coll = db.create_collection(name)
        coll.insert_many(docs)
    except _DB_CONNECT_ERRORS as exc:
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()
        pytest.skip(f"ArangoDB connect/auth failed ({exc!r}); skipping report-only row")

    try:
        yield docs
    finally:
        with contextlib.suppress(Exception):
            # Best-effort teardown — a failed delete shouldn't mask a
            # real test failure upstream.
            db.delete_collection(name)
        client.close()


def connect_session_or_skip(client: "TestClient") -> str:
    """``POST /connect`` via a FastAPI ``TestClient`` and return the
    session token, or ``pytest.skip()`` if the resolved ArangoDB
    credentials/database are unreachable/unauthorized.

    Shared by every ``TestClient``-based report row that previously
    duplicated this as a local ``_connect_session`` function; converts
    what used to be a hard ``assert`` (surfacing as an ERROR-adjacent
    test failure) into the same clean skip every other connect/auth
    failure path in this module uses.
    """
    resp = client.post(
        "/connect",
        json={
            "url": DEFAULT_ARANGO_URL,
            "database": DEFAULT_ARANGO_DB,
            "username": DEFAULT_ARANGO_USER,
            "password": DEFAULT_ARANGO_PASSWORD,
        },
    )
    if resp.status_code != 200:
        pytest.skip(f"/connect failed ({resp.status_code}): {resp.text}; skipping report-only row")
    token = resp.json()["token"]
    assert token
    return token


def connect_session_over_socket_or_skip(port: int) -> str:
    """Raw-socket ``urllib``-based sibling of :func:`connect_session_or_skip`
    for the one report row (``test_first_byte.py``) that binds a real
    ``uvicorn.Server`` instead of using ``TestClient``.
    """
    import json as _json
    import urllib.error
    import urllib.request

    body = _json.dumps(
        {
            "url": DEFAULT_ARANGO_URL,
            "database": DEFAULT_ARANGO_DB,
            "username": DEFAULT_ARANGO_USER,
            "password": DEFAULT_ARANGO_PASSWORD,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/connect",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status != 200:
                pytest.skip(f"/connect failed ({resp.status}); skipping report-only row")
            payload = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        pytest.skip(f"/connect failed ({exc.code}); skipping report-only row")
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        pytest.skip(f"/connect unreachable ({exc!r}); skipping report-only row")
    token = payload["token"]
    assert token
    return token
