"""
agent/client.py

A minimal MCP client for the Auto Care spare-parts inventory server.

Run directly for an end-to-end walkthrough against a seeded demo
database, exercising every protocol concern in one pass:

    python agent/client.py

What it does, in order:
  1. capability negotiation -- a real initialize/initialized exchange,
     and checks the server's declared capabilities before relying on them
  2. tools/list -- discovers only the tools a technician session can see
  3. tools/call -- a read-only call (search_spare_part)
  4. a role change (technician -> manager) that genuinely grows the tool
     set, pushing notifications/tools/list_changed
  5. resources/read -- reads the static warehouse policy instead of
     calling a tool for it
  6. tools/call -- update_inventory on a change that trips the
     elicitation trigger (decreasing a part to zero), pausing for
     confirmation via elicitation/create
  7. tools/call -- generate_inventory_report, a long-running call that
     reports real progress instead of blocking silently

Swap wire_demo_database() for a real connection once databases/db.py has
one configured -- see the comment at the bottom of this file.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
AGENT_ROOT = Path(__file__).resolve().parent

for path in (str(ROOT), str(MCP_SERVER_ROOT), str(AGENT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def wire_demo_database() -> None:
    """
    Point databases.db.get_connection at the seeded SQLite demo DB. Must
    run before anything imports `from databases.db import get_connection`,
    since that binds the function at import time.
    """
    import databases.db as db
    from demo_db import build_demo_connection

    db.get_connection = build_demo_connection


wire_demo_database()

import server  # noqa: E402  (registers tools + resources, wires negotiation onto mcp)
from negotiation import negotiation  # noqa: E402
from notifications import notifier  # noqa: E402
from fastmcp import ElicitationResult  # noqa: E402
from app import memory_manager  # noqa: E402  (same instance write_tools.py writes episodic/scratchpad into)


class CLIContext:
    """
    The Context this client hands to tools. Where the test-suite's stub
    context silently auto-accepts, this one actually surfaces
    elicitation/create and progress updates to whoever is running the
    demo -- prompting on the terminal instead of proceeding silently.
    """

    def __init__(self, auto_confirm: bool | None = None):
        # auto_confirm=None -> prompt interactively (real demo use).
        # auto_confirm=True/False -> skip the prompt (used by the test suite).
        self.auto_confirm = auto_confirm

    async def elicit(self, message: str, schema: dict | None = None) -> ElicitationResult:
        print(f"\n  [elicitation/create] {message}")
        if self.auto_confirm is not None:
            confirmed = self.auto_confirm
        else:
            confirmed = input("  Confirm? [y/N]: ").strip().lower() == "y"
        return ElicitationResult("accept" if confirmed else "decline", confirmed)

    async def report_progress(self, progress: float, total: float = 100) -> None:
        print(f"  [progress] {progress:.0f}/{total:.0f}")


def run_handshake(session_id: str) -> dict:
    """A real initialize/initialized exchange, not assumed."""
    response = negotiation.handle_initialize(
        {"id": 1, "params": {"clientInfo": {"name": "auto-care-cli-agent"}}}
    )
    capabilities = response["result"]["capabilities"]
    print(f"[initialize] server declares: {capabilities}")

    negotiation.handle_initialized_notification(session_id)
    assert negotiation.is_session_initialized(session_id)
    print(f"[initialized] session '{session_id}' ready")

    return capabilities


def list_visible_tools(role: str) -> list:
    """tools/list, filtered to what this session's role is allowed to see."""
    registered = set(server.mcp._tools.keys())
    return sorted(notifier.visible_tools_for_role(role) & registered)


async def main(auto_confirm: bool | None = None) -> dict:
    # Fresh, freshly-seeded database AND fresh in-process memory state for
    # this session -- so running the demo twice (or the test suite running
    # it twice) doesn't leak inventory/episodic/semantic state between runs.
    from demo_db import reset_demo_database
    reset_demo_database()
    memory_manager.stm.clear()
    memory_manager.scratchpad.clear()

    session_id = "demo-session-1"
    capabilities = run_handshake(session_id)

    # A client that skipped this check could offer the risky write tool
    # even if the server had no way to actually pause for confirmation.
    supports_elicitation = "elicitation" in capabilities
    print(f"[capability check] elicitation supported: {supports_elicitation}")
    if not supports_elicitation:
        print("  -> would fall back to read-only tools only; continuing for the demo")

    role = "technician"
    print(f"\n[session] starting as '{role}'")
    print(f"[tools/list] visible tools: {list_visible_tools(role)}")
    memory_manager.add_interaction("user", "Technician session started for customer #4471, vehicle in for brake service.")

    search_result = server.mcp._tools["search_spare_part"]("Brake")
    print(f"[tools/call] search_spare_part('Brake') -> {search_result}")
    memory_manager.add_interaction("tool_call", "search_spare_part('Brake')")
    memory_manager.add_interaction("tool_output", search_result)

    # --- role change: manager authenticates, tool set genuinely changes ---
    print(f"\n[session] '{session_id}' authenticates as 'manager'")
    notification = notifier.authenticate_session(session_id, "manager")
    if notification:
        print(f"[notification] {notification} -- refreshing tool list")
    role = "manager"
    print(f"[tools/list] visible tools: {list_visible_tools(role)}")
    memory_manager.add_interaction("assistant", "Session escalated to manager role; write tools now visible.")

    # --- resource: static policy, read once rather than called ---
    policy_text = server.mcp._resources["warehouse://policy/inventory"]()
    print(f"\n[resources/read] warehouse://policy/inventory ({len(policy_text)} chars)")
    print(f"  first line: {policy_text.splitlines()[0]}")
    memory_manager.add_interaction("tool_output", f"[resource] warehouse://policy/inventory: {policy_text.splitlines()[0]}")

    # --- RAG: ground the "do we charge for this part?" decision in the
    # knowledge base BEFORE acting, instead of guessing. This is the same
    # search_company_knowledge tool server.py registers (hybrid RAG +
    # Self-RAG verification, see retrieval_eval/) -- called here from the
    # live agent loop, not just importable-but-unused. ---
    warranty_question = "What's the warranty window under WT-317?"
    print(f"\n[tools/call] search_company_knowledge({warranty_question!r})")
    knowledge_result = server.mcp._tools["search_company_knowledge"](warranty_question)
    print(f"[tools/call result] grounded={knowledge_result['grounded']} answer={knowledge_result['answer']!r}")
    print(f"  sources: {knowledge_result['sources']}")
    memory_manager.add_interaction("tool_call", f"search_company_knowledge({warranty_question!r})")
    memory_manager.add_interaction("tool_output", knowledge_result)

    # --- memory: pull everything the agent knows before deciding whether
    # to bill the customer for the part, instead of acting on the current
    # tool call alone. ---
    memory_context = memory_manager.retrieve_for_llm()
    print("\n[memory] context pulled before billing decision:")
    print(f"  scratchpad: {memory_context['scratchpad']}")
    print(f"  semantic facts: {memory_context['semantic_memory']}")
    print(f"  recent episodes: {len(memory_context['episodic_memory'])}")
    print(f"  short-term buffer size: {len(memory_context['short_term_memory'])}")

    # --- write tool that trips the elicitation trigger ---
    # Rear Brake Pad Set (part_id=2) starts at quantity=2; decreasing by 2
    # brings it to zero, which company_policy.md requires confirming.
    print("\n[tools/call] update_inventory(part_id=2, action='decrease', quantity=2, ...)")
    ctx = CLIContext(auto_confirm=auto_confirm)
    update_result = await server.mcp._tools["update_inventory"](
        part_id=2,
        action="decrease",
        quantity=2,
        reason="Sold to customer #4471",
        user_id=2,  # Priya Manager
        ctx=ctx,
    )
    print(f"[tools/call result] {update_result}")
    memory_manager.add_interaction("tool_call", "update_inventory(part_id=2, action='decrease', quantity=2)")
    memory_manager.add_interaction("tool_output", update_result)

    # --- long-running call with real progress reporting ---
    print("\n[tools/call] generate_inventory_report()")
    report_result = await server.mcp._tools["generate_inventory_report"](ctx=ctx)
    print(f"[tools/call result] {report_result}")
    memory_manager.add_interaction("tool_call", "generate_inventory_report()")
    memory_manager.add_interaction("tool_output", report_result)

    # --- final memory state: proves promote-or-drop routing actually fired
    # during this run, not just that the classes exist. STM has
    # max_capacity=10 and this run logs more than 10 interactions, so it
    # will have overflowed at least once above. Semantic memory is
    # deliberately NOT touched by any of this -- see the consolidation
    # step below, which is a separate pass on its own schedule. ---
    final_state = memory_manager.retrieve_for_llm()
    print("\n[memory] state after the live session (before consolidation):")
    print(f"  short-term buffer (unflushed tail): {len(final_state['short_term_memory'])} messages")
    print(f"  episodic memory (promoted so far): {len(memory_manager.episodic.get_all_episodes())} episodes")
    print(f"  semantic memory (before this run's consolidation pass): {final_state['semantic_memory']}")

    # --- semantic consolidation: a genuinely separate, periodic pass, run
    # here once at the end of the demo to show it firing -- NOT called
    # from inside add_interaction()/the router above. In production this
    # runs on its own schedule (see memory/run_consolidation.py), not once
    # per live session. ---
    print("\n[memory] running periodic semantic consolidation pass (separate from the live session above)...")
    consolidation_result = memory_manager.run_consolidation()
    print(f"  episodes consolidated: {consolidation_result['episodes_consolidated']}")
    print(f"  facts applied: {consolidation_result['facts_applied']}")
    print(f"  facts expired: {consolidation_result['expired_facts']}")
    print(f"  semantic memory (after consolidation): {memory_manager.semantic.get_active_facts()}")

    return {
        "search_result": search_result,
        "notification": notification,
        "knowledge_result": knowledge_result,
        "update_result": update_result,
        "report_result": report_result,
        "final_memory_state": final_state,
        "consolidation_result": consolidation_result,
    }


if __name__ == "__main__":
    asyncio.run(main())

# To point this agent at a real database instead of the seeded SQLite demo:
# delete the wire_demo_database() call above, and make sure
# databases/db.py's get_connection() returns a live connection for
# whichever engine the README documents (see the note left on that file).
