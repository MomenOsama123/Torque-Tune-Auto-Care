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


def test_purchase_order_graph_below_threshold_auto_submits_no_hitl():
    """A batch under PO_APPROVAL_THRESHOLD_USD should go straight to the
    supplier without a manager pause."""
    from state_graph.graphs.purchase_order_graph import build_graph, record_supplier_reply

    compiled = build_graph().compile()
    tid = _tid()
    # Lower the seeded NAPA batch below threshold by topping up quantity
    # first, then create a small, cheap low-stock part instead.
    conn = db.get_connection()
    conn.execute("UPDATE SpareParts SET quantity = 10 WHERE part_number = 'BRK-002'")
    conn.execute(
        "INSERT INTO SpareParts (part_name, part_number, category_id, supplier_id, quantity, "
        "price, location, minimum_stock, status) VALUES "
        "('Cabin Air Filter', 'NAP-777', 1, 1, 1, 5.00, 'C1-01', 3, 'active')"
    )
    conn.commit()
    conn.close()

    result = compiled.invoke(tid, {"user_id": 2})
    assert result.status == "paused_external"
    assert result.node_name == "submit_po_to_supplier"
    assert result.state["current_batch"]["total_cost"] < 250.0

    resumed = record_supplier_reply(tid, "confirmed", note="Ships next week")
    assert resumed.status == "completed"
    assert resumed.state["final_status"] == "completed"


def test_purchase_order_graph_above_threshold_requires_hitl_then_confirms():
    from state_graph.graphs.purchase_order_graph import (
        build_graph,
        record_manager_decision,
        record_supplier_reply,
    )

    compiled = build_graph().compile()
    tid = _tid()
    paused = compiled.invoke(tid, {"user_id": 2})  # seeded NAPA batch is $312, above $250
    assert paused.status == "paused_hitl"
    assert paused.node_name == "await_manager_po_approval"
    assert paused.state["current_batch"]["total_cost"] >= 250.0

    approved = record_manager_decision(tid, True)
    assert approved.status == "paused_external"
    assert approved.state["po_code"].startswith("PO-")

    final = record_supplier_reply(tid, "confirmed", note="Ships in 5 business days")
    assert final.status == "completed"
    assert final.state["batch_results"] == [
        {"supplier_name": "NAPA Distribution", "outcome": "confirmed"}
    ]


def test_purchase_order_graph_manager_declines_skips_batch():
    from state_graph.graphs.purchase_order_graph import build_graph, record_manager_decision

    compiled = build_graph().compile()
    tid = _tid()
    compiled.invoke(tid, {"user_id": 2})
    result = record_manager_decision(tid, False)
    assert result.status == "completed"
    assert result.state["batch_results"] == [
        {"supplier_name": "NAPA Distribution", "outcome": "declined_by_manager"}
    ]


def test_purchase_order_graph_escalates_supplier_with_no_contact_email():
    from state_graph.graphs.purchase_order_graph import (
        build_graph,
        record_manager_decision,
        record_supplier_reply,
    )

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO Suppliers (name) VALUES ('NoContact Parts Co.')")
    sid = cur.lastrowid
    cur.execute(
        "INSERT INTO SpareParts (part_name, part_number, category_id, supplier_id, quantity, "
        "price, location, minimum_stock, status) VALUES "
        "('Widget', 'NCX-001', 1, ?, 1, 10.0, 'Z9-01', 5, 'active')",
        (sid,),
    )
    conn.commit()
    conn.close()

    compiled = build_graph().compile()
    tid = _tid()
    result = compiled.invoke(tid, {"user_id": 2})  # NAPA batch ($312) sorts first -> HITL
    assert result.status == "paused_hitl"
    result = record_manager_decision(tid, True)
    assert result.status == "paused_external"
    result = record_supplier_reply(tid, "confirmed", note="ok")
    assert result.status == "completed"
    outcomes = {r["supplier_name"]: r["outcome"] for r in result.state["batch_results"]}
    assert outcomes["NoContact Parts Co."] == "escalated_missing_contact"


def test_purchase_order_graph_malformed_supplier_reply_files_a_ticket():
    from state_graph.graphs.purchase_order_graph import (
        build_graph,
        record_manager_decision,
        record_supplier_reply,
    )
    from state_graph.tickets import list_tickets

    compiled = build_graph().compile()
    tid = _tid()
    compiled.invoke(tid, {"user_id": 2})
    record_manager_decision(tid, True)
    result = record_supplier_reply(tid, "idk-call-us-later", note="unclear")
    assert result.status == "failed"
    assert result.ticket_id is not None

    open_tickets = [t for t in list_tickets(status="open") if t.thread_id == tid]
    assert len(open_tickets) == 1
    assert open_tickets[0].node_name == "submit_po_to_supplier"


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


# ---------------------------------------------------------------------
# Warranty Claim graph -- state_graph/graphs/warranty_graph.py
# ---------------------------------------------------------------------


def test_warranty_claim_wear_reason_excluded_by_policy_within_window():
    """A plain wear claim on a brakes-category TorqueParts Direct part
    hits WT-100's wear-exclusion clause -- ground_in_warranty_policy's
    RAG lookup surfaces that exclusion text, and with no manufacturing-
    defect override in the stated reason the claim is correctly refused
    by policy even though it's well inside the 18-month base window."""
    from state_graph.graphs.warranty_graph import build_graph

    compiled = build_graph().compile()
    result = compiled.invoke(
        _tid(),
        {
            "part_id": 4,
            "user_id": 2,
            "inventory_log_id": 1,
            "claim_reason": "wear on rotor surface",
        },
    )
    assert result.status == "completed"
    assert result.state["final_status"] == "not_eligible"
    assert result.state["policy_grounded"] is True


def test_warranty_claim_approved_on_first_submission_needs_no_appeal():
    from state_graph.graphs.warranty_graph import build_graph, record_supplier_reply

    compiled = build_graph().compile()
    tid = _tid()
    paused = compiled.invoke(
        tid,
        {
            "part_id": 4,
            "user_id": 2,
            "inventory_log_id": 1,
            "claim_reason": "manufacturing defect in caliper mount, not wear",
        },
    )
    assert paused.status == "paused_external"

    resumed = record_supplier_reply(tid, "approved", note="Defect confirmed on inspection")
    assert resumed.status == "completed"
    assert resumed.state["final_status"] == "approved"


def test_warranty_claim_rejection_triggers_hitl_appeal_above_threshold():
    """Full loop: reject -> Tree-of-Thoughts appeal argument -> HITL
    (claim value >= APPEAL_APPROVAL_THRESHOLD_USD) -> manager approves ->
    second external wait -> supplier approves the appeal."""
    from state_graph.graphs.warranty_graph import (
        build_graph,
        record_manager_decision,
        record_supplier_reply,
    )

    compiled = build_graph().compile()
    tid = _tid()
    paused = compiled.invoke(
        tid,
        {
            "part_id": 4,
            "user_id": 2,
            "inventory_log_id": 1,
            "claim_reason": "manufacturing defect in caliper mount, not wear",
        },
    )
    assert paused.status == "paused_external"

    rejected = record_supplier_reply(tid, "rejected", note="Photos inconclusive")
    assert rejected.status == "paused_hitl"
    assert rejected.state["appeal_argument"]

    manager_approved = record_manager_decision(tid, True)
    assert manager_approved.status == "paused_external"

    final = record_supplier_reply(tid, "approved", note="Appeal accepted")
    assert final.status == "completed"
    assert final.state["final_status"] == "approved"


def test_warranty_claim_manager_declines_appeal_cancels_thread():
    from state_graph.graphs.warranty_graph import (
        build_graph,
        record_manager_decision,
        record_supplier_reply,
    )

    compiled = build_graph().compile()
    tid = _tid()
    compiled.invoke(
        tid,
        {
            "part_id": 4,
            "user_id": 2,
            "inventory_log_id": 1,
            "claim_reason": "manufacturing defect in caliper mount, not wear",
        },
    )
    record_supplier_reply(tid, "rejected", note="Photos inconclusive")
    final = record_manager_decision(tid, False)
    assert final.status == "completed"
    assert final.state["final_status"] == "appeal_cancelled"


def test_warranty_claim_malformed_supplier_reply_files_a_ticket_not_a_retry():
    """A supplier reply the graph can't parse is the "wrong resubmission
    wastes the claim window" failure mode -- it must become a Ticket
    (engine catches the raised ValueError), NOT get silently retried or
    guessed at."""
    from state_graph.graphs.warranty_graph import build_graph, record_supplier_reply
    from state_graph.tickets import list_tickets

    compiled = build_graph().compile()
    tid = _tid()
    compiled.invoke(
        tid,
        {
            "part_id": 4,
            "user_id": 2,
            "inventory_log_id": 1,
            "claim_reason": "manufacturing defect",
        },
    )
    result = record_supplier_reply(tid, "maybe-later??", note="unclear reply from portal")
    assert result.status == "failed"
    assert result.ticket_id is not None

    open_tickets = [t for t in list_tickets(status="open") if t.thread_id == tid]
    assert len(open_tickets) == 1
    assert open_tickets[0].node_name == "submit_claim_to_supplier"
