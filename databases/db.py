"""Database helpers for the inventory MCP server."""

from __future__ import annotations

import os
from typing import Any


def get_connection() -> Any:
    """Return a database connection for the configured environment.

    The project is designed to work with SQL Server, but the tests and local
    smoke checks use monkeypatching to replace this function. Keeping a simple
    fallback here makes the modules import cleanly and avoids hard failures in
    test environments that do not have a live database.
    """

    raise RuntimeError(
        "No database connection configured. Provide a real connection in this "
        "environment or monkeypatch get_connection during tests."
    )
