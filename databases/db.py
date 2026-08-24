"""Database helpers for the inventory MCP server."""

from __future__ import annotations

import os
from typing import Any


def get_connection() -> Any:
    """Return a database connection for the configured environment.

    Three real paths exist for this function, and this module intentionally
    implements only the first:

    1. Live SQL Server, via the DB_CONNECTION_STRING env var (see
       .env.example). This was previously documented but never actually
       read anywhere in the codebase -- that gap is what this function now
       closes. pyodbc is imported lazily, only when DB_CONNECTION_STRING is
       actually set, so this module keeps importing cleanly in every
       environment that doesn't use this path (matching the existing
       docstring's design goal below).
    2. The seeded SQLite demo database (agent/demo_db.py). This is wired in
       by the app's real entrypoints -- agent/client.py's and
       state_graph/bootstrap.py's wire_demo_database()/ensure_wired() --
       which monkeypatch this exact function at import time, before any
       other module does `from databases.db import get_connection`. That
       wiring is not reproduced here on purpose: whichever entrypoint
       imports this module first is responsible for it, so a forgotten
       wiring call fails loudly (see the raise below) instead of silently
       falling back to a connection nothing asked for.
    3. Tests replace this function entirely via monkeypatch (see
       conftest.py's demo_db_connection fixture) rather than going through
       either path above.

    Keeping a raising fallback here (when neither DB_CONNECTION_STRING is
    set nor a wiring/monkeypatch has run) makes modules import cleanly and
    avoids hard failures in test environments that do not have a live
    database.
    """

    conn_str = os.environ.get("DB_CONNECTION_STRING")
    if conn_str:
        import pyodbc  # local import: only required when a real SQL Server target is configured

        return pyodbc.connect(conn_str)

    raise RuntimeError(
        "No database connection configured. Set DB_CONNECTION_STRING for a "
        "real SQL Server instance, use agent/client.py's or "
        "state_graph/bootstrap.py's demo-database wiring for the seeded "
        "SQLite database, or monkeypatch get_connection during tests."
    )
