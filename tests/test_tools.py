import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = PROJECT_ROOT / "mcp-server"

sys.path.insert(0, str(MCP_SERVER))
# ============================================================
# READ TOOLS
# ============================================================

from tools.read_tools import (
    search_spare_part,
    check_stock,
    suggest_alternative,
)


class TestSearchSparePart:

    @patch("tools.read_tools.get_connection")
    def test_search_spare_part_found(self, mock_get_connection):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchall.return_value = [
            (1, "Brake Pad", 20)
        ]

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        result = search_spare_part("Brake")

        cursor.execute.assert_called_once_with(
            "SELECT * FROM SpareParts WHERE part_name LIKE ?",
            ("%Brake%",)
        )

        assert result == [
            (1, "Brake Pad", 20)
        ]

        conn.close.assert_called_once()


    @patch("tools.read_tools.get_connection")
    def test_search_spare_part_not_found(self, mock_get_connection):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchall.return_value = []

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        with pytest.raises(
            ValueError,
            match="No spare parts found with the given name."
        ):
            search_spare_part("Unknown Part")

        conn.close.assert_called_once()


class TestCheckStock:

    @patch("tools.read_tools.get_connection")
    def test_check_stock_found(self, mock_get_connection):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchone.return_value = (15,)

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        result = check_stock(1)

        cursor.execute.assert_called_once_with(
            "SELECT quantity FROM SpareParts WHERE id = ?",
            (1,)
        )

        assert result == {
            "part_id": 1,
            "quantity": 15
        }

        conn.close.assert_called_once()


    @patch("tools.read_tools.get_connection")
    def test_check_stock_part_not_found(self, mock_get_connection):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchone.return_value = None

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        with pytest.raises(
            ValueError,
            match="Part not found."
        ):
            check_stock(999)

        conn.close.assert_called_once()


class TestSuggestAlternative:

    @patch("tools.read_tools.get_connection")
    def test_suggest_alternative_found(self, mock_get_connection):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchall.return_value = [
            ("Alternative Brake Pad",),
            ("Compatible Brake Pad",)
        ]

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        result = suggest_alternative(1)

        assert result == [
            ("Alternative Brake Pad",),
            ("Compatible Brake Pad",)
        ]

        conn.close.assert_called_once()


    @patch("tools.read_tools.get_connection")
    def test_suggest_alternative_not_found(self, mock_get_connection):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchall.return_value = []

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        with pytest.raises(
            ValueError,
            match="No alternative parts found for the given part ID."
        ):
            suggest_alternative(999)

        conn.close.assert_called_once()


# ============================================================
# WRITE TOOLS
# ============================================================

from tools.write_tools import (
    add_spare_part,
    delete_spare_part,
    generate_inventory_report,
)


class TestAddSparePart:

    @patch("tools.write_tools.spare_part_added")
    @patch("tools.write_tools.get_connection")
    @patch("tools.write_tools.require_manager")
    def test_add_spare_part_with_id(
        self,
        mock_require_manager,
        mock_get_connection,
        mock_notification
    ):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchone.return_value = None

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        mock_notification.return_value = {
            "event": "inventory.part.added",
            "part_id": 10,
            "part_name": "Brake Pad"
        }

        result = add_spare_part(
            part_id=10,
            part_name="Brake Pad",
            quantity=20,
            user_role="manager"
        )

        mock_require_manager.assert_called_once_with("manager")

        calls = cursor.execute.call_args_list

        assert calls[0].args == (
            "SELECT 1 FROM SpareParts WHERE id = ?",
            (10,)
            )

        assert "INSERT INTO SpareParts" in calls[1].args[0]
        assert calls[1].args[1] == (
            10,
            "Brake Pad",
            20
        )

        conn.commit.assert_called_once()
        conn.close.assert_called_once()

        mock_notification.assert_called_once_with(
            10,
            "Brake Pad"
        )

        assert result["part_id"] == 10


    @patch("tools.write_tools.get_connection")
    @patch("tools.write_tools.require_manager")
    def test_add_spare_part_negative_quantity(
        self,
        mock_require_manager,
        mock_get_connection
    ):
        with pytest.raises(
            ValueError,
            match="Quantity cannot be negative."
        ):
            add_spare_part(
                part_id=10,
                part_name="Brake Pad",
                quantity=-5,
                user_role="manager"
            )

        mock_get_connection.assert_not_called()


    @patch("tools.write_tools.get_connection")
    @patch("tools.write_tools.require_manager")
    def test_add_spare_part_empty_name(
        self,
        mock_require_manager,
        mock_get_connection
    ):
        with pytest.raises(
            ValueError,
            match="Part name cannot be empty."
        ):
            add_spare_part(
                part_id=10,
                part_name="   ",
                quantity=10,
                user_role="manager"
            )

        mock_get_connection.assert_not_called()


class TestDeleteSparePart:

    @patch("tools.write_tools.spare_part_deleted")
    @patch("tools.write_tools.get_connection")
    @patch("tools.write_tools.require_manager")
    def test_delete_spare_part_success(
        self,
        mock_require_manager,
        mock_get_connection,
        mock_notification
    ):
        conn = MagicMock()
        cursor = MagicMock()

        # Part exists
        cursor.fetchone.return_value = (1,)

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        mock_notification.return_value = {
            "event": "inventory.part.deleted",
            "part_id": 1
        }

        result = delete_spare_part(
            part_id=1,
            user_role="manager"
        )

        mock_require_manager.assert_called_once_with("manager")

        conn.commit.assert_called_once()
        conn.close.assert_called_once()

        mock_notification.assert_called_once_with(1)

        assert result["part_id"] == 1


    @patch("tools.write_tools.get_connection")
    @patch("tools.write_tools.require_manager")
    def test_delete_spare_part_not_found(
        self,
        mock_require_manager,
        mock_get_connection
    ):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchone.return_value = None

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        with pytest.raises(
            ValueError,
            match="Spare part not found."
        ):
            delete_spare_part(
                part_id=999,
                user_role="manager"
            )

        conn.commit.assert_not_called()
        conn.close.assert_called_once()
        


# ============================================================
# INVENTORY REPORT
# ============================================================

class TestInventoryReport:

    @pytest.mark.asyncio
    @patch("tools.write_tools.get_connection")
    @patch("tools.write_tools.report_inventory_progress")
    async def test_generate_inventory_report(
        self,
        mock_progress,
        mock_get_connection
    ):
        conn = MagicMock()
        cursor = MagicMock()

        cursor.fetchone.return_value = (
            10,      # total parts
            150,     # total quantity
            125.456  # average price
        )

        conn.cursor.return_value = cursor
        mock_get_connection.return_value = conn

        ctx = MagicMock()

        result = await generate_inventory_report(ctx)

        assert result == {
            "success": True,
            "total_parts": 10,
            "total_quantity": 150,
            "average_price": 125.46
        }

        conn.close.assert_called_once()

        assert mock_progress.await_count == 5

        progress_values = [
            call.args[1]
            for call in mock_progress.await_args_list
        ]

        assert progress_values == [
            0,
            25,
            50,
            75,
            100
        ]