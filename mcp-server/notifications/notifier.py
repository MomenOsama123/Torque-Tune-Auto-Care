"""
Notification helpers for the Spare Parts Inventory Management System.
"""

def inventory_updated(part_id:int,quantity:int):
    return{
        "event":"inventory.updated",
        "message":"inventory updated successfully",
        "part_id":part_id,
        "new_quantity":quantity,
    }
    
def spare_part_added(part_id:int, part_name:str | None = None):
    payload = {
        "event": "inventory.part.added",
        "message": "Spare part added successfully",
        "part_id": part_id,
    }
    if part_name is not None:
        payload["part_name"] = part_name
    return payload


def spare_part_deleted(part_id:int):
    return{
        "event":"inventory.part.deleted",
        "message":"Spare part deleted successfully",
        "part_id":part_id,
    }


# -----------------------------
# Runtime tool-set change: notifications/tools/list_changed
# -----------------------------
# A front-desk/technician session only sees the read-only tools. When that
# session authenticates as manager/admin, update_inventory, add_spare_part,
# and delete_spare_part become available -- and the server pushes
# notifications/tools/list_changed instead of making the client poll or
# reconnect to find out.

READ_ONLY_TOOLS = {
    "search_spare_part",
    "check_stock",
    "suggest_alternative",
    "generate_inventory_report",

}
MANAGER_ONLY_TOOLS = {"update_inventory", "add_spare_part", "delete_spare_part"}

_session_roles: dict[str, str] = {}


def _has_manager_tools(role: str | None) -> bool:
    return bool(role) and role.lower() in {"manager", "admin"}


def visible_tools_for_role(role: str | None) -> set[str]:
    """The tool set a session with this role is allowed to see."""
    if _has_manager_tools(role):
        return READ_ONLY_TOOLS | MANAGER_ONLY_TOOLS
    return set(READ_ONLY_TOOLS)


def build_tools_list_changed_notification() -> dict:
    """The actual notification payload, per the MCP spec -- no params."""
    return {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


def authenticate_session(session_id: str, role: str) -> dict | None:
    """
    Call this when a session's role becomes known or changes (e.g. a
    technician session authenticates as manager). Returns the
    tools/list_changed notification to push if the visible tool set
    actually changed as a result, or None if it didn't -- so the server
    never fires a notification for a role change that changes nothing.
    """
    previous_role = _session_roles.get(session_id)
    _session_roles[session_id] = role

    if _has_manager_tools(previous_role) != _has_manager_tools(role):
        return build_tools_list_changed_notification()
    return None


def reset_sessions() -> None:
    """Test helper -- clears all tracked session roles."""
    _session_roles.clear()
