"""
state_graph/run_demo.py

Run directly for a narrated, end-to-end walkthrough of everything
state_graph/ adds:

    python state_graph/run_demo.py

What it shows, in order:
  1. Graph 1 (fulfillment): a job that resolves without needing approval.
  2. Graph 2 (inventory_approval): a sensitive change that PAUSES for a
     manager (HITL), grounded in real company policy via RAG, then is
     resumed and actually applied to the database.
  3. Graph 3 (knowledge_qa): a warranty question answered from the real
     knowledge base.
  4. A live Crash-and-Resume: starts a thread, then simulates the
     process dying immediately after the first checkpoint by throwing
     away the in-memory graph object and rebuilding everything from
     scratch (a fresh CompiledGraph, fresh imports-equivalent state) --
     resume() proves the thread continues correctly from disk alone.
     (state_graph/tests/test_crash_resume.py additionally proves this
     across a REAL os.kill'd subprocess, not just an in-memory reset.)
  5. A deliberately broken node that raises mid-run -- shows a Failure
     Ticket getting filed and the thread halting instead of crashing the
     whole process.
"""

from __future__ import annotations

from state_graph.bootstrap import ensure_wired  # noqa: F401
import agent.demo_db as demo_db
import databases.db as db
from state_graph.db import reset_db
from state_graph.checkpointer import Checkpointer
from state_graph.tickets import list_tickets


def _setup() -> None:
    reset_db()
    demo_db.reset_demo_database()
    db.get_connection = demo_db.build_demo_connection


def demo_fulfillment() -> None:
    from state_graph.graphs.fulfillment_graph import build_graph

    print("\n=== Graph 1: Fulfillment (Task Decomposition + Tree of Thoughts/LATS) ===")
    compiled = build_graph().compile()
    result = compiled.invoke(
        "demo-fulfillment-1",
        {"job_id": "7001", "required_parts": ["Front Brake Pad Set"]},
    )
    print(f"status={result.status} node={result.node_name}")
    print(f"decision={result.state.get('decision')}")
    print(f"final_status={result.state.get('final_status')}")


def demo_inventory_approval() -> None:
    from state_graph.graphs.inventory_approval_graph import build_graph

    print("\n=== Graph 2: Sensitive Inventory Update (RAG policy check + graph-level HITL) ===")
    compiled = build_graph().compile()
    thread_id = "demo-inventory-1"
    paused = compiled.invoke(
        thread_id,
        {"part_id": 2, "action": "decrease", "quantity": 2, "reason": "Sold to customer #4471", "user_id": 2},
    )
    print(f"status={paused.status} node={paused.node_name}")
    print(f"  sensitive={paused.state.get('sensitive')}  reason={paused.state.get('elicitation_reason')}")
    print(f"  policy check (RAG-grounded): {paused.state.get('policy_check', '')[:120]}...")
    print("  -- thread is now paused on disk; a manager could take hours to respond --")

    print("  [manager approves]")
    resumed = compiled.resume(thread_id, human_response={"approved": True})
    print(f"status={resumed.status} node={resumed.node_name}")
    print(f"  update_result={resumed.state.get('update_result')}")


def demo_knowledge_qa() -> None:
    from state_graph.graphs.knowledge_graph import build_graph

    print("\n=== Graph 3: Knowledge Q&A (RAG Architecture + Constrained-ReAct agentic retry) ===")
    compiled = build_graph().compile()
    result = compiled.invoke("demo-knowledge-1", {"question": "What's the warranty window under WT-317?"})
    print(f"status={result.status} attempts={result.state.get('attempts')}")
    print(f"answer={result.state.get('answer')}")


def demo_crash_and_resume() -> None:
    from state_graph.graphs.fulfillment_graph import build_graph, decompose

    print("\n=== Live Crash-and-Resume ===")
    thread_id = "demo-crash-1"

    # Simulate "process 1": run only the first node, checkpoint it, then
    # stop -- as if the process died right here.
    state = {"thread_id": thread_id, "job_id": "7002", "required_parts": ["Front Brake Pad Set"]}
    state.update(decompose(state))
    Checkpointer().save(
        thread_id=thread_id, graph_name="fulfillment", node_name="decompose", status="running", state=state
    )
    print("  [process 1] ran 'decompose', checkpointed, then crashed (simulated)")
    del state  # nothing left in memory from "process 1"

    # "process 2": nothing but the thread_id and a fresh graph object.
    compiled = build_graph().compile()
    result = compiled.resume(thread_id)
    print(f"  [process 2] resumed -> status={result.status} node={result.node_name}")
    print(f"  [process 2] final decision={result.state.get('decision')}")
    print("  see state_graph/tests/test_crash_resume.py for the same proof across a real os.kill'd process")


def demo_failure_ticket() -> None:
    from state_graph.engine import StateGraph, END

    print("\n=== Failure Ticket on an unexpected Mid-Node error ===")

    def flaky_node(state):
        raise ConnectionError("simulated: downstream supplier API unreachable")

    g = StateGraph("demo_ticket").add_node("flaky", flaky_node)
    g.set_entry_point("flaky").add_edge("flaky", END)
    compiled = g.compile()

    result = compiled.invoke("demo-ticket-1", {})
    print(f"status={result.status} ticket_id={result.ticket_id}")
    open_tickets = list_tickets(status="open")
    print(f"open tickets now: {len(open_tickets)}")
    if open_tickets:
        t = open_tickets[0]
        print(f"  #{t.id} [{t.graph_name}/{t.node_name}] {t.error_type}: {t.error_message}")


def main() -> None:
    _setup()
    demo_fulfillment()
    demo_inventory_approval()
    demo_knowledge_qa()
    demo_crash_and_resume()
    demo_failure_ticket()
    print("\nAll demos completed.")


if __name__ == "__main__":
    main()
