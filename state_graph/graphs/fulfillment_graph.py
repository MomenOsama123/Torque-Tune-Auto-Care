"""
state_graph/graphs/fulfillment_graph.py

State Problem 1: "Prepare spare parts for a repair job when one or more
required parts are out of stock." Multi-turn (3+ nodes), waits on a real
external event when the decision affects cost (HITL manager approval)
and has real consequences for a wrong guess (reserving unavailable
inventory, an incompatible substitute) -- exactly why this is a Stateful
Problem, not a single tool call.

Intelligent techniques embedded in the nodes (reused, not reimplemented):
  - Task Decomposition: planning/fulfillment_decomposition.py
    (build_plan_first / execute_plan_first)
  - Tree of Thoughts (comparing in-stock alternatives) and LATS (the
    final proceed/delay decision): planning/fulfillment_planning.py
    (run_planning_layer), which internally routes each sub-task through
    planning/routing.py's classify_subtask().

Graph shape:

    decompose -> execute_tasks -> plan_decision -*-> notify_customer -> END
                                                  \\-> human_approval -*-> notify_customer -> END
                                                                        \\-> escalate_delay -> END

`human_approval` only fires when plan_decision recommends committing to
an ALTERNATIVE part (a real substitution a manager should sign off on --
delaying never needs approval, it has no downside to reverse).
"""

from __future__ import annotations

from typing import Any

from state_graph.bootstrap import memory_manager
from state_graph.engine import END, StateGraph, interrupt
from planning.fulfillment_decomposition import JobRequest, build_plan_first, execute_plan_first
from planning.fulfillment_planning import run_planning_layer
from planning.model_provider import get_llm

GRAPH_NAME = "fulfillment"


def _job_from_state(state: dict) -> JobRequest:
    return JobRequest(job_id=state["job_id"], required_parts=list(state["required_parts"]))


def decompose(state: dict) -> dict[str, Any]:
    """Task Decomposition: commit to the full worst-case task DAG up
    front (planning/fulfillment_decomposition.build_plan_first)."""
    job = _job_from_state(state)
    plan = build_plan_first(job)
    return {
        "task_count": len(plan.tasks),
        "task_ids": [t.id for t in plan.tasks],
    }


def execute_tasks(state: dict) -> dict[str, Any]:
    """Runs the decomposed plan's real tool calls (check_stock,
    suggest_alternative, ...) via the vendored toolkit's own topological
    batching. Rebuilds the (deterministic, no-LLM) plan from the job
    rather than trying to deserialize the Task/Plan objects out of the
    checkpoint -- see module docstring in state_graph/engine.py on why
    nodes stay self-contained like this."""
    job = _job_from_state(state)
    plan = build_plan_first(job)
    llm = get_llm()
    outputs, telemetry = execute_plan_first(plan, job, llm)
    return {
        "task_outputs": outputs,
        "decomposition_tool_calls": telemetry.tool_calls,
        "decomposition_llm_calls": telemetry.llm_calls,
    }


def plan_decision(state: dict) -> dict[str, Any]:
    """Tree of Thoughts (compare in-stock alternatives, when 2+ exist)
    and LATS (the final proceed/delay recommendation), both via
    planning/fulfillment_planning.run_planning_layer -- unchanged, real
    algorithm code, not re-implemented here."""
    job = _job_from_state(state)
    llm = get_llm()
    result = run_planning_layer(job, state["task_outputs"], llm)
    decision_text = result["final_decision"].output
    return {
        "decision": decision_text,
        "customer_notification": result["customer_notification"],
        "uses_alternative": "proceed-with-alternative" in decision_text.lower(),
    }


def _route_after_decision(state: dict) -> str:
    if state.get("uses_alternative"):
        return "needs_approval"
    return "no_approval_needed"


def human_approval(state: dict) -> Any:
    """Graph-level HITL: pauses the THREAD (survives a killed process,
    unlike the MCP tool's own in-call elicitation) until a manager
    approves committing to a substitute part."""
    if "approved" not in state:
        return interrupt(
            "manager_must_approve_alternative_part",
            decision=state["decision"],
            job_id=state["job_id"],
        )
    return {}  # approved is already in state (set via resume's human_response)


def _route_after_approval(state: dict) -> str:
    return "approved" if state.get("approved") else "rejected"


def notify_customer(state: dict) -> dict[str, Any]:
    memory_manager.add_interaction(
        "planning",
        {
            "job_id": state["job_id"],
            "decision": state["decision"],
            "customer_notification": state["customer_notification"],
            "approved_by_manager": state.get("approved"),
        },
    )
    return {"final_status": "notified"}


def escalate_delay(state: dict) -> dict[str, Any]:
    memory_manager.add_interaction(
        "planning",
        {
            "job_id": state["job_id"],
            "decision": "delay",
            "reason": "manager declined the proposed alternative part",
        },
    )
    return {"final_status": "delayed"}


def build_graph() -> StateGraph:
    g = StateGraph(name=GRAPH_NAME)
    g.add_node("decompose", decompose)
    g.add_node("execute_tasks", execute_tasks)
    g.add_node("plan_decision", plan_decision)
    g.add_node("human_approval", human_approval)
    g.add_node("notify_customer", notify_customer)
    g.add_node("escalate_delay", escalate_delay)

    g.set_entry_point("decompose")
    g.add_edge("decompose", "execute_tasks")
    g.add_edge("execute_tasks", "plan_decision")
    g.add_conditional_edges(
        "plan_decision",
        _route_after_decision,
        {"needs_approval": "human_approval", "no_approval_needed": "notify_customer"},
    )
    g.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {"approved": "notify_customer", "rejected": "escalate_delay"},
    )
    g.add_edge("notify_customer", END)
    g.add_edge("escalate_delay", END)
    return g
