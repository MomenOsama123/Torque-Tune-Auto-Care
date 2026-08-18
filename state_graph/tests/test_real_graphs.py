"""End-to-end tests for the three real graphs against the seeded demo
database -- these are the actual Stateful Problems, not synthetic
stand-ins."""

import uuid

import pytest

from state_graph.bootstrap import ensure_wired  # noqa: F401 -- import-time wiring
import agent.demo_db as demo_db
import databases.db as db
from state_graph.db import reset_db


@pytest.fixture(autouse=True)
def fresh_databases():
    reset_db()
    demo_db.reset_demo_database()
    db.get_connection = demo_db.build_demo_connection
    yield


def _tid() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


def test_fulfillment_graph_delay_path_completes_without_approval():
    from state_graph.graphs.fulfillment_graph import build_graph

    compiled = build_graph().compile()
    result = compiled.invoke(
        _tid(),
        {"job_id": "9001", "required_parts": ["Timing Belt"]},  # discontinued, qty 0, no alt
    )
    assert result.status == "completed"
    assert result.state["final_status"] == "notified"


def test_fulfillment_graph_proceed_path_needs_no_approval():
    from state_graph.graphs.fulfillment_graph import build_graph

    compiled = build_graph().compile()
    result = compiled.invoke(
        _tid(),
        {"job_id": "9002", "required_parts": ["Front Brake Pad Set"]},  # in stock (qty=8)
    )
    assert result.status == "completed"
    assert result.state["uses_alternative"] is False


def test_inventory_approval_graph_pauses_for_sensitive_change_then_applies():
    from state_graph.graphs.inventory_approval_graph import build_graph

    compiled = build_graph().compile()
    tid = _tid()
    # Rear Brake Pad Set (id=2) has qty=2; decreasing by 2 zeroes it out -> sensitive.
    paused = compiled.invoke(
        tid,
        {"part_id": 2, "action": "decrease", "quantity": 2, "reason": "Sold to customer", "user_id": 2},
    )
    assert paused.status == "paused_hitl"
    assert paused.state["sensitive"] is True

    resumed = compiled.resume(tid, human_response={"approved": True})
    assert resumed.status == "completed"
    assert resumed.state["update_result"]["new_quantity"] == 0


def test_inventory_approval_graph_rejection_cancels_without_writing():
    from state_graph.graphs.inventory_approval_graph import build_graph

    compiled = build_graph().compile()
    tid = _tid()
    compiled.invoke(
        tid,
        {"part_id": 2, "action": "decrease", "quantity": 2, "reason": "Sold to customer", "user_id": 2},
    )
    resumed = compiled.resume(tid, human_response={"approved": False})
    assert resumed.status == "completed"
    assert resumed.state["final_status"] == "cancelled"


def test_inventory_approval_graph_skips_approval_for_small_change():
    from state_graph.graphs.inventory_approval_graph import build_graph

    compiled = build_graph().compile()
    result = compiled.invoke(
        _tid(),
        {"part_id": 1, "action": "increase", "quantity": 1, "reason": "Restock", "user_id": 2},
    )
    assert result.status == "completed"
    assert result.state["sensitive"] is False


def test_knowledge_graph_answers_a_grounded_question():
    from state_graph.graphs.knowledge_graph import build_graph

    compiled = build_graph().compile()
    result = compiled.invoke(_tid(), {"question": "What's the warranty window under WT-317?"})
    assert result.status == "completed"
    assert result.state["final_status"] == "answered"
    assert result.state["attempts"] >= 1
