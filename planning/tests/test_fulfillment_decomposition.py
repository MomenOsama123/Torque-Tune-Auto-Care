"""
planning/tests/test_fulfillment_decomposition.py

Issue 2 verification. Mocks tools.read_tools.get_connection the same way
tests/test_tools.py already does (unittest.mock.patch + MagicMock), so
these tests need no live database, matching this repo's existing
convention. Uses planning/model_provider.py's offline fallback (no
ANTHROPIC_API_KEY needed) -- deterministic, per its own docstring.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_ROOT = ROOT / "mcp-server"
for _p in (str(ROOT), str(MCP_SERVER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from planning.fulfillment_decomposition import (  # noqa: E402
    JobRequest,
    build_plan_first,
    dynamic_fulfillment,
    execute_plan_first,
)
from planning.model_provider import get_llm  # noqa: E402
from planning.vendor.planning_lab.models import Plan, Task  # noqa: E402


# ---------------------------------------------------------------------
# Fake DB, same shape/scenario as planning/fulfillment_demo.py
# ---------------------------------------------------------------------

_PARTS = {
    "Brake Pad": (1, "Brake Pad", 20),
    "Oil Filter": (2, "Oil Filter", 0),
    "Oil Filter XL": (3, "Oil Filter XL", 5),
}
_ALTERNATIVES = {2: [("Oil Filter XL",)], 1: []}


def _fake_cursor():
    cursor = MagicMock()

    def execute(sql, params=()):
        cursor._sql = sql
        cursor._params = params

    def fetchall():
        sql = cursor._sql
        if "FROM SpareParts WHERE part_name LIKE" in sql:
            needle = cursor._params[0].strip("%")
            row = _PARTS.get(needle)
            return [row] if row else []
        if "FROM AlternativeParts" in sql:
            return _ALTERNATIVES.get(cursor._params[0], [])
        return []

    def fetchone():
        sql = cursor._sql
        if "SELECT quantity FROM SpareParts WHERE id" in sql:
            part_id = cursor._params[0]
            for row in _PARTS.values():
                if row[0] == part_id:
                    return (row[2],)
            return None
        return None

    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = fetchall
    cursor.fetchone.side_effect = fetchone
    return cursor


def _fake_connection():
    conn = MagicMock()
    conn.cursor.return_value = _fake_cursor()
    return conn


@pytest.fixture()
def fake_db():
    with patch("tools.read_tools.get_connection", side_effect=_fake_connection):
        yield


# ---------------------------------------------------------------------
# Acyclicity -- inherited from the vendored Plan model, not reimplemented
# ---------------------------------------------------------------------


def test_cyclic_plan_is_rejected():
    """Confirms our code path raises through the vendored toolkit's own
    cycle check (planning_lab/models.py Plan.validate_dag), rather than
    a check we wrote ourselves."""
    with pytest.raises(ValidationError, match="Cycle detected"):
        Plan.model_validate({
            "goal": "Reject an invalid cyclic fulfillment plan",
            "tasks": [
                {"id": "a", "instruction": "depends on b, which depends on a", "depends_on": ["b"]},
                {"id": "b", "instruction": "depends on a, which depends on b", "depends_on": ["a"]},
            ],
        })


def test_build_plan_first_is_a_valid_dag():
    job = JobRequest(job_id="job-1", required_parts=["Brake Pad", "Oil Filter"])
    plan = build_plan_first(job)
    assert plan.topological_order()[-1] == "decide"
    assert plan.execution_batches()[0] == ["check_brake_pad", "check_oil_filter"]


def test_more_than_three_parts_exceeds_the_vendored_8_task_cap():
    """Real constraint discovered in planning_lab/models.py
    (Field(max_length=8)), not invented for this test."""
    job = JobRequest(job_id="job-big", required_parts=["A", "B", "C", "D"])
    with pytest.raises(ValidationError):
        build_plan_first(job)


# ---------------------------------------------------------------------
# Real divergence: dynamic skips work decomposition-first always pays for
# ---------------------------------------------------------------------


def test_dynamic_skips_unneeded_alternative_search(fake_db):
    """Brake Pad has plenty of stock (quantity=20). decomposition-first
    still runs suggest_alternative() for it because that branch is
    committed to the plan before any check_stock result exists. Dynamic
    decomposition observes quantity=20 first and, grounded in that real
    result, never looks for a Brake Pad alternative at all."""
    job = JobRequest(job_id="job-42", required_parts=["Brake Pad", "Oil Filter"])
    llm = get_llm()

    plan = build_plan_first(job)
    pf_outputs, pf_telemetry = execute_plan_first(plan, job, llm)
    dyn_history, dyn_telemetry = dynamic_fulfillment(job, llm)

    assert "altsearch_brake_pad" in pf_outputs
    assert pf_outputs["altsearch_brake_pad"] == "Brake Pad: alternatives=[none]"

    assert not any(task_id == "altsearch:Brake Pad" for task_id, _ in dyn_history)

    assert dyn_telemetry.tool_calls < pf_telemetry.tool_calls
    assert "suggest_alternative(1)" in pf_telemetry.tool_call_log
    assert "suggest_alternative(1)" not in dyn_telemetry.tool_call_log


def test_both_methods_route_the_out_of_stock_part_through_its_alternative(fake_db):
    job = JobRequest(job_id="job-42", required_parts=["Brake Pad", "Oil Filter"])
    llm = get_llm()

    plan = build_plan_first(job)
    pf_outputs, _ = execute_plan_first(plan, job, llm)
    dyn_history, _ = dynamic_fulfillment(job, llm)

    assert "Oil Filter XL (qty=5)" in pf_outputs["altsearch_oil_filter"]
    dyn_altsearch = next(r for t, r in dyn_history if t == "altsearch:Oil Filter")
    assert "Oil Filter XL (qty=5)" in dyn_altsearch


def test_offline_llm_never_hits_the_network(fake_db):
    """get_llm() with no ANTHROPIC_API_KEY set must return the offline
    double, never attempt a real call -- keeps this test suite runnable
    with no key/network, per this repo's existing convention."""
    import os

    assert "ANTHROPIC_API_KEY" not in os.environ or not os.environ["ANTHROPIC_API_KEY"]
    job = JobRequest(job_id="job-smoke", required_parts=["Brake Pad"])
    llm = get_llm()
    plan = build_plan_first(job)
    outputs, _ = execute_plan_first(plan, job, llm)
    assert outputs["decide"].startswith("mock heuristic:")
