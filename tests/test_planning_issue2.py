"""Compatibility tests for the current Week-4 fulfillment decomposition API.

The old test imported planning.spare_parts_decomposition, which was removed
when the implementation was consolidated into fulfillment_decomposition.py.
These tests exercise the current public API against a real in-memory SQLite
DB and verify the static/dynamic planning distinction without mocks for the
SQL tool calls.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

from tools import read_tools  # noqa: E402
from planning.fulfillment_decomposition import (  # noqa: E402
    JobRequest,
    build_plan_first,
    dynamic_fulfillment,
)


@pytest.fixture
def spare_parts_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE SpareParts (
            id INTEGER PRIMARY KEY,
            part_name TEXT NOT NULL,
            part_number TEXT,
            category_id INTEGER,
            supplier_id INTEGER,
            quantity INTEGER NOT NULL,
            price REAL,
            location TEXT,
            minimum_stock INTEGER,
            status TEXT
        );
        CREATE TABLE AlternativeParts (
            id INTEGER PRIMARY KEY,
            part_id INTEGER NOT NULL,
            alternative_part_id INTEGER NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO SpareParts (id, part_name, part_number, category_id, supplier_id, quantity, price, location, minimum_stock, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "Brake Pad Set - Front", "BP-1023", 1, 1, 12, 450.0, "Shelf A3", 5, "active"),
            (2, "Brake Disc - Standard", "BD-2050", 1, 2, 0, 620.0, "Shelf A6", 4, "active"),
            (3, "Brake Disc - Premium", "BD-2051", 1, 2, 15, 780.0, "Shelf A7", 4, "active"),
        ],
    )
    conn.execute("INSERT INTO AlternativeParts (part_id, alternative_part_id) VALUES (2, 3)")
    conn.commit()

    class KeepOpenConnection:
        def cursor(self):
            return conn.cursor()

        def close(self):
            pass

    monkeypatch.setattr(read_tools, "get_connection", lambda: KeepOpenConnection())
    yield conn
    conn.close()


def test_static_plan_is_valid_and_contains_required_branches(spare_parts_db):
    job = JobRequest(
        job_id="job-test",
        required_parts=["Brake Pad Set - Front", "Brake Disc - Standard"],
    )
    plan = build_plan_first(job)

    assert len(plan.tasks) <= 8
    ids = {task.id for task in plan.tasks}
    assert any("check_stock" in task_id for task_id in ids)
    assert any("alternatives" in task_id for task_id in ids)

    # The toolkit Plan validates the dependency graph during construction.
    assert len(plan.execution_batches()) >= 1


def test_dynamic_decomposition_observes_stock_before_opening_alt_branch(spare_parts_db):
    job = JobRequest(job_id="job-test", required_parts=["Brake Pad Set - Front"])

    class OfflineLLM:
        def invoke(self, messages, **kwargs):
            class Response:
                content = "Proceed with the originally requested part."
            return Response()

        def with_structured_output(self, schema, *, method):
            return self

    history, telemetry = dynamic_fulfillment(job, OfflineLLM())
    assert history
    # A stocked part should not require an alternative search.
    tool_names = [entry[0] for entry in telemetry.tool_call_log]
    assert "suggest_alternative" not in tool_names
