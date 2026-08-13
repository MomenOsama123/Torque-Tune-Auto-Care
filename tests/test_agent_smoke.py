import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import client  # noqa: E402  (agent/client.py)


def test_agent_end_to_end_walkthrough_confirmed():
    """
    Runs the full handshake -> discover -> role-change -> resource ->
    elicitation -> progress flow with the confirmation auto-accepted, and
    checks every concern actually fired.
    """
    result = asyncio.run(client.main(auto_confirm=True))

    # search_spare_part found the seeded "Brake" parts.
    assert result["search_result"]

    # The technician -> manager role change genuinely changed the visible
    # tool set, so a tools/list_changed notification was pushed.
    assert result["notification"] == {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed",
    }

    # The confirmed elicitation let the change through.
    assert result["update_result"]["event"] == "inventory.updated"
    assert result["update_result"]["new_quantity"] == 0

    # The report tool completed and returned real numbers.
    assert result["report_result"]["success"] is True
    assert result["report_result"]["total_parts"] >= 1


def test_agent_end_to_end_walkthrough_declined():
    """Same flow, but the human declines the elicitation -- the change
    must not be applied."""
    result = asyncio.run(client.main(auto_confirm=False))

    assert result["update_result"]["success"] is False


def test_capability_check_reflects_server_declaration():
    session_id = "capability-check-session"
    capabilities = client.run_handshake(session_id)

    assert "elicitation" in capabilities
    assert capabilities["tools"]["listChanged"] is True


def test_technician_cannot_see_manager_only_tools():
    assert "update_inventory" not in client.list_visible_tools("technician")
    assert "update_inventory" in client.list_visible_tools("manager")