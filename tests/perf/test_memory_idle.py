"""Report-only memory-ceiling row (idle) — PRD §9.4 (D-09).

PRD §9.4 row: **Memory ceiling, idle** — target p95 ≤ 250 MiB RSS,
Report-only tier.

Gated behind ``RUN_INTEGRATION=1`` + a real ``docker-compose``
ArangoDB, matching every other Docker-dependent report row in this
suite (D-09's row list groups memory/concurrency/first-byte alongside
``/sparql`` GET and ``/schema/introspect`` as needing the real
docker-compose ArangoDB) — a single ``/connect`` warms the process
into the same "live, connected" state the other report rows measure
from, rather than an isolated pure-Python memory reading that doesn't
reflect the service's real footprint.

Measured via the stdlib ``resource`` module (no new dependency, no
``psutil``): :func:`resource.getrusage` ``ru_maxrss`` is a *peak*
RSS-so-far counter, platform-unit-dependent (KiB on Linux, bytes on
Darwin) — :func:`_rss_mib` normalises both to MiB.

**Unit note (shared with ``test_memory_load.py``):** ``append_report``
(Plan 01) is a generic ``(row_name, value, budget)`` appender written
for millisecond p95 rows; its column header literally reads "p95
(ms)". Reusing it here for a MiB-valued row is a deliberate,
documented choice (rather than forking a second Markdown table shape
for two rows) — the row name itself carries the ``_rss_mib_p95``
unit suffix so a human reviewer is never misled by the fixed column
header.
"""

from __future__ import annotations

import resource
import sys
import time
from collections.abc import Iterator

import pytest

from tests.perf.conftest import append_report, connect_session_or_skip, live_arango_or_skip, p95

pytestmark = pytest.mark.perf

_N_SAMPLES = 3  # p95() needs >= 2 points; ru_maxrss is a monotonic peak.
_BUDGET_MIB = 250.0


def _rss_mib() -> float:
    """Return the process's peak RSS so far, normalised to MiB.

    ``ru_maxrss`` is KiB on Linux, bytes on Darwin/BSD — verified
    against the stdlib ``resource`` docs (platform-dependent unit is
    called out explicitly there).
    """

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024


@pytest.fixture(scope="module")
def _live_arango() -> Iterator[None]:
    """Module-scoped Docker + connect/auth gate — see
    ``tests/perf/conftest.py``'s :func:`live_arango_or_skip` (never
    ERRORs on a connect/auth failure; skip-gates instead)."""

    live_arango_or_skip()
    yield


def test_memory_idle_rss_p95(_live_arango: None) -> None:
    """Report-only RSS row after one real ``/connect`` handshake, no
    further load. Never asserts against the §9.4 budget (D-09) — only
    appends the measured MiB figure to ``LATENCY_REPORT.md``.
    """

    from fastapi.testclient import TestClient

    from arango_sparql.service import app

    client = TestClient(app)
    connect_session_or_skip(client)

    samples: list[float] = []
    for _ in range(_N_SAMPLES):
        samples.append(_rss_mib())
        time.sleep(0.05)

    measured = p95(samples)
    append_report("memory_idle_rss_mib_p95", measured, _BUDGET_MIB)
