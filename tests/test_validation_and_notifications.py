import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
if str(MCP_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_ROOT))

from notifications.notifier import (  # noqa: E402
    inventory_updated,
    spare_part_added,
    spare_part_deleted,
)
from validation.validators import (  # noqa: E402
    AuthorizationError,
    ElicitationRequired,
    ValidationError,
    authorize_update_inventory,
    validate_update_inventory,
)


def test_authorize_update_inventory_allows_manager_roles() -> None:
    authorize_update_inventory("manager")
    authorize_update_inventory("admin")


def test_authorize_update_inventory_rejects_non_managers() -> None:
    with pytest.raises(AuthorizationError):
        authorize_update_inventory("technician")


def test_validate_update_inventory_rejects_discontinued_parts() -> None:
    with pytest.raises(ValidationError):
        validate_update_inventory("set", 5, 10, "discontinued", "Restock")


def test_validate_update_inventory_requires_reason_for_every_change() -> None:
    with pytest.raises(ValidationError):
        validate_update_inventory("set", 5, 10, "active", "   ")


def test_validate_update_inventory_requests_confirmation_for_zero_stock() -> None:
    result = validate_update_inventory("decrease", 10, 10, "active", "Sold")

    assert isinstance(result, ElicitationRequired)
    assert result.proposed_new_quantity == 0


def test_validate_update_inventory_requests_confirmation_for_large_decrease() -> None:
    result = validate_update_inventory("decrease", 25, 50, "active", "Inventory correction")

    assert isinstance(result, ElicitationRequired)
    assert result.proposed_new_quantity == 25


def test_notification_helpers_return_consistent_payloads() -> None:
    assert inventory_updated(7, 12) == {
        "event": "inventory.updated",
        "message": "inventory updated successfully",
        "part_id": 7,
        "new_quantity": 12,
    }

    assert spare_part_added(7, "Brake Pad") == {
        "event": "inventory.part.added",
        "message": "Spare part added successfully",
        "part_id": 7,
        "part_name": "Brake Pad",
    }

    assert spare_part_deleted(7) == {
        "event": "inventory.part.deleted",
        "message": "Spare part deleted successfully",
        "part_id": 7,
    }
