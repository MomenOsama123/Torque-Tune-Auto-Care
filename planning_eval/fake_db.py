"""
planning_eval/fake_db.py

Issue 7. The SAME fake-database convention already established three
times over (planning/tests/test_fulfillment_decomposition.py,
test_grounded_environment.py, test_self_correction.py -- all patch
tools.read_tools.get_connection with a MagicMock whose cursor matches on
the real SQL text mcp-server/tools/read_tools.py actually sends),
factored into one reusable builder so planning_eval's scenarios don't
each re-paste the same ~35 lines. Not a second mocking system -- same
SQL substrings, same behaviour, one place to change if read_tools.py's
queries ever change.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def _make_cursor(parts: dict[str, tuple], alternatives: dict[int, list[tuple]]):
    cursor = MagicMock()

    def execute(sql, params=()):
        cursor._sql = sql
        cursor._params = params

    def fetchall():
        sql = cursor._sql
        if "FROM SpareParts WHERE part_name LIKE" in sql:
            needle = cursor._params[0].strip("%")
            row = parts.get(needle)
            return [row] if row else []
        if "FROM AlternativeParts" in sql:
            return alternatives.get(cursor._params[0], [])
        return []

    def fetchone():
        sql = cursor._sql
        if "SELECT quantity FROM SpareParts WHERE id" in sql:
            part_id = cursor._params[0]
            for row in parts.values():
                if row[0] == part_id:
                    return (row[2],)
            return None
        return None

    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = fetchall
    cursor.fetchone.side_effect = fetchone
    return cursor


def _make_connection(parts, alternatives):
    conn = MagicMock()
    conn.cursor.return_value = _make_cursor(parts, alternatives)
    return conn


@contextmanager
def patched_db(parts: dict[str, tuple], alternatives: dict[int, list[tuple]]):
    """parts: {part_name: (id, part_name, quantity)}
    alternatives: {part_id: [(alt_part_name,), ...]}
    Same shapes tools/read_tools.py's real rows have."""
    with patch("tools.read_tools.get_connection", side_effect=lambda: _make_connection(parts, alternatives)):
        yield


__all__ = ["patched_db"]
