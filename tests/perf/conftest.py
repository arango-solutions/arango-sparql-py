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
  (``statistics.quantiles(samples, n=100)[93]`` for p95), matching this
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

import json
import statistics
from pathlib import Path
from typing import Any

# Re-exposed (not duplicated) fake ArangoDB double + connect helper — see
# module docstring above. ``fake_client_factory`` is a ``pytest.fixture``;
# re-exporting it here makes it collectible by any test under
# ``tests/perf/`` without a perf-specific copy of the ~140-line double.
from tests.test_service_sparql_routes import (
    _FakeArangoClient,
    _FakeCursor,
    _FakeDb,
    _connect_session,
    fake_client_factory,
)

__all__ = [
    "_FakeArangoClient",
    "_FakeCursor",
    "_FakeDb",
    "_connect_session",
    "fake_client_factory",
    "p95",
    "load_baseline",
    "append_report",
]

# Only the three CI-gated rows (D-08) live in ``baseline.json`` — the
# report-only rows (D-09) are recorded solely in ``LATENCY_REPORT.md``.
BASELINE_PATH = Path(__file__).parent / "baseline.json"
LATENCY_REPORT_PATH = Path(__file__).parent / "LATENCY_REPORT.md"


def p95(samples: list[float]) -> float:
    """Return the 95th percentile of ``samples`` (stdlib-only, no numpy/scipy).

    Uses ``statistics.quantiles(samples, n=100)[93]`` per RESEARCH.md's
    "Don't Hand-Roll" guidance — index 93 is the boundary between the 94th
    and 95th percentile bucket in a 100-way split, i.e. p95.
    """
    ordered = sorted(samples)
    return statistics.quantiles(ordered, n=100)[93]


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
