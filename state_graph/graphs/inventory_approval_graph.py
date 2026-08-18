"""
state_graph/graphs/inventory_approval_graph.py

State Problem 2: a sensitive inventory change (one that would zero out
stock, or a large decrease) needs a manager's sign-off before it is
applied. `update_inventory` in mcp-server/tools/write_tools.py already
elicits a confirmation -- but that elicitation lives INSIDE one async
call: if the process holding it dies (or the manager doesn't answer for
hours), the request is gone. This graph is the same approval turned into
a real, resumable, multi-turn Stateful Problem: it can be paused for
however long a manager takes to respond, checkpointed to disk, and
resumed by a completely different process later.

Intelligent techniques embedded in the nodes:
  - RAG Architecture: `ground_in_policy` calls the real, already-built
    hybrid-RAG + Self-RAG-verified `search_company_knowledge` tool to
    check whether a specific company policy exception applies (e.g. a
    warranty-mandated replacement) BEFORE deciding whether this change
    still needs manager approval -- an actual document lookup, not a
    hardcoded rule.
  - Constrained ReAct: the node sequence itself is a reason -> act loop
    restricted to a fixed action set {check_policy, request_approval,
    apply, reject} -- the graph's edges ARE the constraint (no action
    outside that set is reachable), mirroring a Constrained ReAct
    controller without needing a separate free-text ReAct prompt loop
    for what is fundamentally a small, auditable decision.

Graph shape:

    authorize_and_validate -*-> ground_in_policy -*-> apply_update -> log -> END
                             \\-> apply_update (not sensitive)         \\
                                                                        await_human_approval -*-> apply_update -> log -> END
                                                                                               \\-> cancelled -> END
"""

from __future__ import annotations

import asyncio
from typing import Any

from state_graph.bootstrap import GraphContext, memory_manager, server
from state_graph.engine import END, StateGraph, interrupt

from databases.db import get_connection
from validation.validators import (
    AuthorizationError,
    ValidationError,
    ElicitationRequired,
    authorize_update_inventory,
    validate_update_inventory,
)

GRAPH_NAME = "inventory_approval"


def authorize_and_validate(state: dict) -> dict[str, Any]:
    """Reads the real Torque Tune demo DB (same tables update_inventory
    itself reads) to authorize the caller and determine whether this
    specific change is sensitive -- raises normally (-> a Failure
    Ticket) for anything genuinely unexpected, e.g. a part_id that
    doesn't exist."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM Users WHERE id = ?", (state["user_id"],))
        row = cur.fetchone()
        if row is None:
            raise AuthorizationError(f"User {state['user_id']} not found.")
        authorize_update_inventory(row[0])

        cur.execute("SELECT quantity, status FROM SpareParts WHERE id = ?", (state["part_id"],))
        part_row = cur.fetchone()
        if part_row is None:
            raise ValueError(f"Spare part {state['part_id']} not found.")
        current_quantity, part_status = part_row
    finally:
        conn.close()

    outcome = validate_update_inventory(
        action=state["action"],
        quantity=state["quantity"],
        current_quantity=current_quantity,
        part_status=part_status,
        reason=state["reason"],
    )
    sensitive = isinstance(outcome, ElicitationRequired)
    return {
        "current_quantity": current_quantity,
        "part_status": part_status,
        "sensitive": sensitive,
        "elicitation_reason": outcome.reason if sensitive else None,
    }


def _route_after_validate(state: dict) -> str:
    return "sensitive" if state["sensitive"] else "not_sensitive"


def ground_in_policy(state: dict) -> dict[str, Any]:
    """RAG Architecture: check the real knowledge base for a policy
    exception before deciding this still needs a human -- e.g. a
    warranty-mandated replacement may be pre-approved by policy."""
    question = (
        f"Does company policy pre-approve inventory adjustments for reason: "
        f"{state['reason']!r} without manager confirmation?"
    )
    result = server.mcp._tools["search_company_knowledge"](question)
    policy_exempts = result["grounded"] and "pre-approved" in result["answer"].lower()
    return {
        "policy_check": result["answer"],
        "policy_grounded": result["grounded"],
        "policy_exempts": policy_exempts,
    }


def _route_after_policy(state: dict) -> str:
    return "exempt" if state.get("policy_exempts") else "needs_approval"


def await_human_approval(state: dict) -> Any:
    if "approved" not in state:
        return interrupt(
            "manager_must_approve_sensitive_change",
            part_id=state["part_id"],
            elicitation_reason=state["elicitation_reason"],
            policy_check=state.get("policy_check"),
        )
    return {}


def _route_after_approval(state: dict) -> str:
    return "approved" if state.get("approved") else "rejected"


def apply_update(state: dict) -> dict[str, Any]:
    """Actually applies the change through the REAL MCP tool
    (mcp-server/tools/write_tools.py's update_inventory) so authorization,
    validation, InventoryLogs writes, and notifications all run through
    the one tested code path -- this graph never writes SpareParts /
    InventoryLogs itself."""
    ctx = GraphContext(auto_confirm=True)  # human already approved at graph level, if this was sensitive
    result = asyncio.run(
        server.mcp._tools["update_inventory"](
            part_id=state["part_id"],
            action=state["action"],
            quantity=state["quantity"],
            reason=state["reason"],
            user_id=state["user_id"],
            ctx=ctx,
        )
    )
    return {"update_result": result}


def log_and_finish(state: dict) -> dict[str, Any]:
    memory_manager.add_interaction(
        "tool_output",
        {"tool": "update_inventory", "graph_thread": state["thread_id"], "result": state["update_result"]},
    )
    return {"final_status": "applied"}


def cancelled(state: dict) -> dict[str, Any]:
    memory_manager.add_interaction(
        "assistant",
        f"Inventory change for part {state['part_id']} cancelled -- manager declined approval.",
    )
    return {"final_status": "cancelled"}


def build_graph() -> StateGraph:
    g = StateGraph(name=GRAPH_NAME)
    g.add_node("authorize_and_validate", authorize_and_validate)
    g.add_node("ground_in_policy", ground_in_policy)
    g.add_node("await_human_approval", await_human_approval)
    g.add_node("apply_update", apply_update)
    g.add_node("log_and_finish", log_and_finish)
    g.add_node("cancelled", cancelled)

    g.set_entry_point("authorize_and_validate")
    g.add_conditional_edges(
        "authorize_and_validate",
        _route_after_validate,
        {"sensitive": "ground_in_policy", "not_sensitive": "apply_update"},
    )
    g.add_conditional_edges(
        "ground_in_policy",
        _route_after_policy,
        {"exempt": "apply_update", "needs_approval": "await_human_approval"},
    )
    g.add_conditional_edges(
        "await_human_approval",
        _route_after_approval,
        {"approved": "apply_update", "rejected": "cancelled"},
    )
    g.add_edge("apply_update", "log_and_finish")
    g.add_edge("log_and_finish", END)
    g.add_edge("cancelled", END)
    return g
