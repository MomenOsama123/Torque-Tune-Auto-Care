import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
if str(MCP_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_ROOT))

from negotiation.negotiation import (  # noqa: E402
    SERVER_CAPABILITIES,
    handle_initialize,
    handle_initialized_notification,
    is_session_initialized,
)
from notifications.notifier import (  # noqa: E402
    MANAGER_ONLY_TOOLS,
    READ_ONLY_TOOLS,
    authenticate_session,
    reset_sessions,
    visible_tools_for_role,
)


# -----------------------------
# Capability negotiation
# -----------------------------

def test_initialize_declares_elicitation_and_tools_listchanged():
    response = handle_initialize(
        {"id": 1, "params": {"clientInfo": {"name": "test-client"}}}
    )

    assert response["result"]["capabilities"] == SERVER_CAPABILITIES
    assert "elicitation" in response["result"]["capabilities"]
    assert response["result"]["capabilities"]["tools"]["listChanged"] is True


def test_session_not_initialized_until_notification_arrives():
    assert is_session_initialized("session-a") is False
    handle_initialized_notification("session-a")
    assert is_session_initialized("session-a") is True


# -----------------------------
# Runtime tool-set change / tools/list_changed
# -----------------------------

def test_technician_session_only_sees_read_only_tools():
    assert visible_tools_for_role("technician") == READ_ONLY_TOOLS


def test_manager_authentication_pushes_tools_list_changed():
    reset_sessions()

    # First time we see this session, nothing has "changed" yet.
    first = authenticate_session("session-b", "technician")
    assert first is None
    assert visible_tools_for_role("technician") == READ_ONLY_TOOLS

    # Same session authenticates as manager -> tool set genuinely grows.
    second = authenticate_session("session-b", "manager")
    assert second == {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}
    assert visible_tools_for_role("manager") == READ_ONLY_TOOLS | MANAGER_ONLY_TOOLS


def test_reauthenticating_with_the_same_role_does_not_push_a_notification():
    reset_sessions()
    authenticate_session("session-c", "manager")

    notification = authenticate_session("session-c", "manager")

    assert notification is None