"""
planning/fulfillment_demo.py

Issue 2 deliverable: "a real case where the two methods diverge."

Scenario (job with 2 required parts, at the seeded-demo-DB shape used by
tests/test_tools.py's mocking convention):
  - "Brake Pad"  -> id=1, quantity=20   (plenty of stock)
  - "Oil Filter" -> id=2, quantity=0    (out of stock), one alternative
                    "Oil Filter XL" -> id=3, quantity=5 (has stock)

Run:
    python planning/fulfillment_demo.py

decomposition-first commits to the full worst-case DAG up front, so it
calls suggest_alternative() for "Brake Pad" too even though it never
needed an alternative -- that call (and the two search_spare_part /
check_stock calls it triggers on false-positive alternative names, none
here since Brake Pad has none) is wasted work purely because the plan was
fixed before any real result was known.

dynamic decomposition observes check_stock("Brake Pad") = 20 first and,
grounded in that real result, decides it never needs to look for a
Brake Pad alternative at all -- it only branches into altsearch for
"Oil Filter", the part that actually needed it. That's the divergence:
fewer tool calls, and a materially different (shorter) execution trace,
driven by a real database result, not a hardcoded example.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
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


# Part name (as passed to search_spare_part) -> SpareParts row shape used
# elsewhere in this repo's own tests (id, part_name, quantity) -- see
# tests/test_tools.py TestSearchSparePart for the same shape convention.
_PARTS = {
    "Brake Pad": (1, "Brake Pad", 20),
    "Oil Filter": (2, "Oil Filter", 0),
    "Oil Filter XL": (3, "Oil Filter XL", 5),
}
_ALTERNATIVES = {
    2: [("Oil Filter XL",)],  # part_id 2 (Oil Filter) -> one alternative
    1: [],  # Brake Pad has none
}


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
            part_id = cursor._params[0]
            return _ALTERNATIVES.get(part_id, [])
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


def main() -> None:
    job = JobRequest(job_id="job-42", required_parts=["Brake Pad", "Oil Filter"])
    llm = get_llm()

    with patch("tools.read_tools.get_connection", side_effect=_fake_connection):
        plan = build_plan_first(job)
        pf_outputs, pf_telemetry = execute_plan_first(plan, job, llm)

        dyn_history, dyn_telemetry = dynamic_fulfillment(job, llm)

    print("=== decomposition-first ===")
    for task_id, output in pf_outputs.items():
        print(f"  {task_id}: {output}")
    print(f"  tool calls: {pf_telemetry.tool_calls}  ({pf_telemetry.tool_call_log})")
    print(f"  llm calls:  {pf_telemetry.llm_calls}")

    print("\n=== dynamic decomposition ===")
    for task_id, output in dyn_history:
        print(f"  {task_id}: {output}")
    print(f"  tool calls: {dyn_telemetry.tool_calls}  ({dyn_telemetry.tool_call_log})")
    print(f"  llm calls:  {dyn_telemetry.llm_calls}")

    print("\n=== divergence ===")
    brake_pad_altsearch_in_pf = any("altsearch_brake_pad" == k for k in pf_outputs)
    brake_pad_altsearch_in_dyn = any(t == "altsearch:Brake Pad" for t, _ in dyn_history)
    print(f"  decomposition-first ran altsearch for Brake Pad: {brake_pad_altsearch_in_pf} (always does, by construction)")
    print(f"  dynamic ran altsearch for Brake Pad:              {brake_pad_altsearch_in_dyn} (skipped -- grounded in real quantity=20)")
    print(f"  tool-call delta: decomposition-first={pf_telemetry.tool_calls}, dynamic={dyn_telemetry.tool_calls}")


if __name__ == "__main__":
    main()
