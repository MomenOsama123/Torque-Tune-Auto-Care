"""
tests/test_planning_issue2.py

Issue 2 -- Task Decomposition tests.

Uses a real sqlite3 database (in-memory, schema mirrors databases/schema.sql
for the columns the read tools actually touch) and monkeypatches
tools.read_tools.get_connection to return it. This runs the *real*
search_spare_part / check_stock / suggest_alternative SQL against a real
connection -- not a MagicMock standing in for query results -- for a
stronger "real DB interaction" check than the existing mocked unit tests
in tests/test_tools.py (which this file does not replace or modify).

Fixture data is deliberately crafted (not databases/seed.sql) so the
divergence between static and dynamic decomposition is deterministic and
reproducible:

  Part 1 "Brake Pad Set - Front" (id=1): quantity=12, needed=5 -> SUFFICIENT.
      No AlternativeParts row exists for id=1.
  Part 2 "Brake Disc - Standard"  (id=2): quantity=0,  needed=2 -> INSUFFICIENT.
  Part 3 "Brake Disc - Premium"   (id=3): quantity=15 -> the alternative for id=2.
  AlternativeParts: (part_id=2 -> alternative_part_id=3)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import networkx as nx
import pydantic
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = PROJECT_ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

from tools import read_tools  # noqa: E402  (path must be set up first, matches test_tools.py)

from planning.spare_parts_decomposition import (  # noqa: E402
    PartRequirement,
    build_static_part_plan,
    dynamic_decompose_part,
    execute_static_plan,
    prepare_job_dynamic,
    prepare_job_static,
)
from planning.vendor.planning_lab.models import Plan, Task  # noqa: E402


# ---------------------------------------------------------------------
# Fixture: a real sqlite3 connection seeded with the scenario above.
# ---------------------------------------------------------------------
@pytest.fixture
def spare_parts_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute(
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
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE AlternativeParts (
            id INTEGER PRIMARY KEY,
            part_id INTEGER NOT NULL,
            alternative_part_id INTEGER NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO SpareParts (id, part_name, part_number, category_id, supplier_id, "
        "quantity, price, location, minimum_stock, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "Brake Pad Set - Front", "BP-1023", 1, 1, 12, 450.0, "Shelf A3", 5, "active"),
            (2, "Brake Disc - Standard", "BD-2050", 1, 2, 0, 620.0, "Shelf A6", 4, "active"),
            (3, "Brake Disc - Premium", "BD-2051", 1, 2, 15, 780.0, "Shelf A7", 4, "active"),
        ],
    )
    conn.execute(
        "INSERT INTO AlternativeParts (part_id, alternative_part_id) VALUES (2, 3)"
    )
    conn.commit()

    class _KeepOpenConnection:
        """sqlite3.Connection.close is read-only on the object itself, and
        the real tool functions call conn.close() after every single call
        -- wrap the connection so that per-call close() is a no-op and the
        in-memory database survives the whole test."""

        def __init__(self, real_conn):
            self._real = real_conn

        def cursor(self):
            return self._real.cursor()

        def commit(self):
            self._real.commit()

        def close(self):
            pass

    wrapped = _KeepOpenConnection(conn)
    monkeypatch.setattr(read_tools, "get_connection", lambda: wrapped)
    yield conn
    conn.close()


# ---------------------------------------------------------------------
# 1. Static decomposition creates a valid DAG
# ---------------------------------------------------------------------
def test_static_plan_is_a_valid_dag():
    plan = build_static_part_plan(PartRequirement("Brake Pad Set - Front", 5))
    assert isinstance(plan, Plan)
    assert len(plan.tasks) == 6
    assert len(plan.tasks) <= 8  # respects the vendored 8-task limit
    assert nx.is_directed_acyclic_graph(plan.graph)
    assert plan.topological_order()[0] == "search"
    assert plan.topological_order()[-1] == "outcome"


# ---------------------------------------------------------------------
# 2. Cyclic DAGs are rejected (uses the toolkit's own validator; no
#    duplicate cycle-detection logic is added anywhere in planning/).
# ---------------------------------------------------------------------
def test_cyclic_plan_is_rejected():
    a = Task(id="a", instruction="depends on b, which depends on a", depends_on=["b"])
    b = Task(id="b", instruction="depends on a, which depends on b", depends_on=["a"])
    with pytest.raises((pydantic.ValidationError, ValueError)):
        Plan(goal="a cyclic plan that must be rejected", tasks=[a, b])


# ---------------------------------------------------------------------
# 3. Dynamic decomposition reacts to the actual stock result
# ---------------------------------------------------------------------
def test_dynamic_stops_after_sufficient_stock(spare_parts_db):
    outcome = dynamic_decompose_part(PartRequirement("Brake Pad Set - Front", 5))
    assert outcome.fulfilled is True
    assert outcome.source == "original"
    task_ids = [t.task_id for t in outcome.trace]
    assert task_ids == ["search", "check"]  # never reaches suggest_alt
    assert outcome.tool_calls == 2


def test_dynamic_continues_after_insufficient_stock(spare_parts_db):
    outcome = dynamic_decompose_part(PartRequirement("Brake Disc - Standard", 2))
    assert outcome.fulfilled is True
    assert outcome.source == "alternative"
    task_ids = [t.task_id for t in outcome.trace]
    assert task_ids == ["search", "check", "suggest_alt", "search_alt", "check_alt"]
    assert outcome.tool_calls == 5


# ---------------------------------------------------------------------
# 4. Alternative handling follows:
#    suggest_alternative -> search_spare_part -> check_stock
# ---------------------------------------------------------------------
def test_alternative_resolution_order(spare_parts_db):
    outcome = dynamic_decompose_part(PartRequirement("Brake Disc - Standard", 2))
    actions = [t.action for t in outcome.trace]
    assert actions == [
        "search_spare_part",
        "check_stock",
        "suggest_alternative",
        "search_spare_part(alt)",
        "check_stock(alt)",
    ]
    alt_step = outcome.trace[3]
    assert alt_step.result == {"part_id": 3, "part_name": "Brake Disc - Premium"}


# ---------------------------------------------------------------------
# 5. Static and dynamic approaches produce a real observable divergence
# ---------------------------------------------------------------------
def test_static_and_dynamic_diverge_on_sufficient_part(spare_parts_db):
    requirement = PartRequirement("Brake Pad Set - Front", 5)

    static_outcome = execute_static_plan(build_static_part_plan(requirement), requirement)
    dynamic_outcome = dynamic_decompose_part(requirement)

    # Both agree on the *result* ...
    assert static_outcome.fulfilled == dynamic_outcome.fulfilled is True
    assert static_outcome.source == dynamic_outcome.source == "original"

    # ... but static explored predetermined work dynamic skipped: it still
    # ran suggest_alt (which found nothing, since part 1 has no
    # AlternativeParts row) purely because the graph was fixed up front.
    static_actions = [t.action for t in static_outcome.trace]
    dynamic_actions = [t.action for t in dynamic_outcome.trace]
    assert "suggest_alternative" in static_actions
    assert "suggest_alternative" not in dynamic_actions
    assert static_outcome.tool_calls == 3
    assert dynamic_outcome.tool_calls == 2
    assert static_outcome.tool_calls > dynamic_outcome.tool_calls


def test_static_and_dynamic_agree_on_insufficient_part(spare_parts_db):
    """No divergence expected here: the alternative work is genuinely
    needed, so both approaches do the same real tool calls."""
    requirement = PartRequirement("Brake Disc - Standard", 2)

    static_outcome = execute_static_plan(build_static_part_plan(requirement), requirement)
    dynamic_outcome = dynamic_decompose_part(requirement)

    assert static_outcome.tool_calls == dynamic_outcome.tool_calls == 5
    assert static_outcome.source == dynamic_outcome.source == "alternative"


def test_job_level_divergence_across_multiple_parts(spare_parts_db):
    requirements = [
        PartRequirement("Brake Pad Set - Front", 5),   # sufficient -> diverges
        PartRequirement("Brake Disc - Standard", 2),   # insufficient -> agrees
    ]

    static_results = prepare_job_static(requirements)
    dynamic_results = prepare_job_dynamic(requirements)

    static_total = sum(o.tool_calls for o in static_results.values())
    dynamic_total = sum(o.tool_calls for o in dynamic_results.values())

    assert static_total == 3 + 5  # 8
    assert dynamic_total == 2 + 5  # 7
    assert static_total > dynamic_total
    for req in requirements:
        assert static_results[req.part_name].fulfilled == dynamic_results[req.part_name].fulfilled