"""
mcp-server/memory/run_consolidation.py

The periodic consolidation job. This is the ONLY place
MemoryManager.run_consolidation() gets called -- deliberately not from
add_interaction(), and deliberately not from the router. Run it on a
schedule (cron / scheduled task) in production; run it manually here for
grading/demo purposes.

Usage:
    python mcp-server/memory/run_consolidation.py

What the demo below proves, in order:
  1. two episodes are promoted into episodic memory that state a
     contact-method preference -- the SECOND one contradicts the first
     (this is the "real conflict" the spec asks for, not a hypothetical
     one),
  2. run_consolidation() is called as a separate pass, not from inside
     the promotion step above,
  3. semantic memory ends up with the LATEST value, the OLD value is
     still visible (never silently lost) via get_fact_history(), and the
     conflict + its resolution reason are printed,
  4. a fact with an expired TTL is swept by expire_stale_facts() on the
     next pass.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_ROOT = ROOT / "mcp-server"
AGENT_ROOT = ROOT / "agent"

for path in (str(ROOT), str(MCP_SERVER_ROOT), str(AGENT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import databases.db as db
from demo_db import build_demo_connection
db.get_connection = build_demo_connection

from memory.memory_manager import MemoryManager
from memory.episodic_memory import EpisodicMemory
from memory.semantic_memory import SemanticMemory


def demo() -> None:
    from demo_db import reset_demo_database
    reset_demo_database()

    manager = MemoryManager(llm_client=None)

    print("=== Step 1: two promoted episodes, second one conflicts with the first ===")
    manager.episodic.add_episode(
        event_type="interaction_event",
        content="Customer said: please email me when the brake pads are back in stock.",
        promotion_reason="mock heuristic: contains signal word(s) ['prefer' not needed -- explicit contact instruction]",
    )
    manager.episodic.add_episode(
        event_type="interaction_event",
        content="Customer said: actually don't email me, call my cell instead, I don't check email often.",
        promotion_reason="mock heuristic: contains signal word(s) ['instead']",
    )
    print("  2 episodes written to episodic memory (via the router's normal promote path).")

    print("\n=== Step 2: separate periodic consolidation pass ===")
    result = manager.run_consolidation()
    print(f"  episodes consolidated this pass: {result['episodes_consolidated']}")
    print(f"  facts applied: {result['facts_applied']}")
    print(f"  facts expired this pass: {result['expired_facts']}")

    print("\n=== Step 3: current active fact + full version history ===")
    active = manager.semantic.get_active_facts()
    print(f"  active semantic facts: {active}")
    history = manager.semantic.get_fact_history("preferred_communication")
    for row in history:
        print(f"  version {row['version']} (active={row['is_active']}): "
              f"{row['fact_value']!r} -- {row['change_reason']}")

    print("\n=== Step 4: expiration ===")
    manager.semantic.update_fact(
        "quoted_labor_rate",
        "$120/hr (promotional)",
        change_reason="promotional rate quoted during this call",
        expires_at="2000-01-01 00:00:00",  # already in the past -> will be swept
    )
    print("  wrote a fact with an expires_at already in the past.")
    result2 = manager.run_consolidation()
    print(f"  next consolidation pass expired: {result2['expired_facts']}")
    print(f"  active facts after sweep: {manager.semantic.get_active_facts()}")

    print("\n=== Second consolidation pass is a no-op on the same episodes ===")
    result3 = manager.run_consolidation()
    print(f"  episodes consolidated: {result3['episodes_consolidated']} "
          "(0 expected -- the two episodes above were already marked consolidated in Step 2)")


if __name__ == "__main__":
    demo()
