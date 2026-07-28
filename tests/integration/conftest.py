"""Shared infrastructure for tests that need a live ArangoDB.

Hosts a tiny set of helper functions that boot ArangoDB on demand via
``docker compose up -d arangodb``. Both the existing
``tests/integration/test_execute_endpoint.py`` integration suite and
the W3C live-execution harness (``tests/w3c/test_w3c_live_execution.py``)
depend on the same ``docker compose`` workflow, so the helpers live in
one place to keep the boot policy consistent.

The helpers are intentionally exposed as plain functions rather than
pytest fixtures: pytest auto-loads ``conftest.py`` only for tests under
the same directory, but Python imports the module just fine from
anywhere — so callers under ``tests/w3c/`` simply ``from
tests.integration.conftest import ...`` and reuse the same boot logic.

No state is owned here. All bootstrap is best-effort and ``False`` is
returned (rather than raising) when Docker is unavailable so callers
can ``pytest.skip(...)`` cleanly.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

DEFAULT_ARANGO_HOST = os.getenv("ARANGO_HOST", "localhost")
# Default host port is 8532, not the canonical 8529, so this
# project's test ArangoDB never collides with sibling-project
# containers that may already be bound to 8529. Mirrors the
# host-side mapping in ``docker-compose.yml``; override via
# ``ARANGO_PORT`` (or the full ``ARANGO_URL``) when pointing at
# an externally-managed ArangoDB.
DEFAULT_ARANGO_PORT = int(os.getenv("ARANGO_PORT", "8532"))
DEFAULT_ARANGO_URL = os.getenv("ARANGO_URL", f"http://{DEFAULT_ARANGO_HOST}:{DEFAULT_ARANGO_PORT}")
DEFAULT_ARANGO_USER = os.getenv("ARANGO_USER", "root")
DEFAULT_ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD", "rootpw")
# Prefer an explicit test-DB override, then the service's configured
# ``ARANGO_DB``, then a dedicated ``sparql-to-aql`` default — anything
# but ``_system`` so the suite never drops/recreates collections in the
# ArangoDB catalogue database. The DB is auto-provisioned by the
# fixtures (``ensure_test_database``) since it may not exist yet.
_resolved_arango_db = os.getenv("ARANGO_TEST_DB") or os.getenv("ARANGO_DB") or "sparql-to-aql"
if _resolved_arango_db == "_system":
    # Never trust an ambient ``_system`` resolution regardless of which
    # env var it came from — this repo's own dev ``.env`` sets
    # ``ARANGO_DB=_system``, and an import-order race can leak that
    # value into this module's resolution before a test-only override
    # is in effect (see 04-07-PLAN.md's hardening fix). A report-only
    # perf row or test fixture must never run against the ArangoDB
    # catalogue database, full stop.
    _resolved_arango_db = "sparql-to-aql"
DEFAULT_ARANGO_DB = _resolved_arango_db


def ensure_test_database() -> None:
    """Best-effort: create :data:`DEFAULT_ARANGO_DB` if it is missing.

    Integration / W3C-live fixtures call this before opening the database
    so a fresh ``sparql-to-aql`` (or operator-chosen ``ARANGO_DB``) works
    without a manual provisioning step. ``_system`` is skipped — it
    always exists. Failures propagate to the caller's connection attempt,
    which already surfaces a clear skip/error.
    """
    if DEFAULT_ARANGO_DB == "_system":
        return
    from arango import ArangoClient

    from arango_sparql.arango_admin import ensure_database

    client = ArangoClient(hosts=DEFAULT_ARANGO_URL.rstrip("/"))
    try:
        ensure_database(
            client,
            DEFAULT_ARANGO_DB,
            username=DEFAULT_ARANGO_USER,
            password=DEFAULT_ARANGO_PASSWORD,
        )
    finally:
        client.close()


def integration_enabled() -> bool:
    """Return ``True`` iff ``RUN_INTEGRATION`` is set to a truthy value.

    Exposed as a function (not a constant) so tests can import it after
    setting the env var inside a single test session, e.g. via
    ``monkeypatch``. Mirrors the gate that
    ``tests/integration/test_execute_endpoint.py`` already uses; lifting
    it here keeps both suites in lockstep on what "integration mode"
    means.
    """
    return os.getenv("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")


def arangodb_reachable(
    host: str = DEFAULT_ARANGO_HOST,
    port: int = DEFAULT_ARANGO_PORT,
    *,
    timeout_s: float = 1.0,
) -> bool:
    """Cheap TCP probe — returns ``True`` iff a TCP connect to
    ``host:port`` succeeds within ``timeout_s`` seconds.

    Used as a pre-flight before paying the ``python-arango`` client
    cost: if nothing is listening, the caller can fall back to
    :func:`try_boot_arangodb_via_compose` instead of hitting an
    auth-handshake timeout.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _repo_root() -> Path:
    """Resolve the repo root from this file's location.

    ``tests/integration/conftest.py`` → up two levels. We don't rely on
    ``cwd`` because pytest may be invoked from anywhere.
    """
    return Path(__file__).resolve().parents[2]


def try_boot_arangodb_via_compose(
    *,
    timeout_s: float = 60.0,
    compose_file: Path | None = None,
) -> bool:
    """Best-effort ``docker compose up -d arangodb`` then poll the
    container until TCP becomes reachable.

    Returns ``False`` (rather than raising) when:

    * ``docker-compose.yml`` is missing,
    * the ``docker`` binary isn't on ``PATH``,
    * ``docker compose`` fails (no daemon, image pull errors, …),
    * the boot exceeds ``timeout_s``.

    Callers translate a ``False`` return into a ``pytest.skip(...)`` so
    a developer without Docker still gets a clean test run.
    """
    repo_root = _repo_root()
    compose_yml = compose_file or (repo_root / "docker-compose.yml")
    if not compose_yml.is_file():
        return False
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_yml), "up", "-d", "arangodb"],
            check=True,
            capture_output=True,
            timeout=30.0,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if arangodb_reachable():
            # ArangoDB accepts TCP before it accepts authenticated
            # requests; a brief pause lets the auth subsystem warm up
            # so the very first request after boot doesn't 401.
            time.sleep(2.0)
            return True
        time.sleep(1.0)
    return False
