import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
if str(MCP_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_ROOT))

import tools.read_tools as read_tools
import tools.write_tools as write_tools
from fastmcp import Context


class DummyCursor:
    def __init__(self, rows=None, fetchone_sequence=None):
        self.rows = rows or []
        self.executed = []
        # For handlers that call fetchone() more than once (e.g. a role
        # lookup, then a part lookup), pass the results in call order here.
        self._fetchone_sequence = list(fetchone_sequence) if fetchone_sequence else None

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if self._fetchone_sequence is not None:
            return self._fetchone_sequence.pop(0) if self._fetchone_sequence else None
        return self.rows[0] if self.rows else None

    @property
    def lastrowid(self):
        return 42


class DummyConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commit_calls = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commit_calls += 1

    def close(self):
        self.closed = True


def test_search_spare_part_returns_matching_rows(monkeypatch):
    cursor = DummyCursor([("Brake Pad",)])
    conn = DummyConnection(cursor)
    monkeypatch.setattr(read_tools, "get_connection", lambda: conn)

    result = read_tools.search_spare_part("Brake")

    assert result == [("Brake Pad",)]
    assert cursor.executed


def test_update_inventory_commits_without_elicitation_for_small_increase(monkeypatch):
    # First fetchone() = role lookup for user_id, second = part lookup.
    cursor = DummyCursor(fetchone_sequence=[("manager",), (10, "active")])
    conn = DummyConnection(cursor)
    monkeypatch.setattr(write_tools, "get_connection", lambda: conn)
    monkeypatch.setattr(
        write_tools,
        "inventory_updated",
        lambda part_id, new_quantity: {
            "part_id": part_id,
            "new_quantity": new_quantity,
            "event": "inventory.updated",
        },
    )

    result = asyncio.run(
        write_tools.update_inventory(
            part_id=1,
            action="increase",
            quantity=2,
            reason="Restock from supplier",
            user_id=7,
            ctx=Context(),
        )
    )

    assert result["event"] == "inventory.updated"
    assert result["part_id"] == 1
    assert result["new_quantity"] == 12
    assert conn.commit_calls == 1
    assert conn.closed is True


def test_update_inventory_cancels_when_elicitation_declined(monkeypatch):
    # A decrease to zero requires elicitation; make the stub decline it.
    cursor = DummyCursor(fetchone_sequence=[("manager",), (10, "active")])
    conn = DummyConnection(cursor)
    monkeypatch.setattr(write_tools, "get_connection", lambda: conn)

    class DecliningContext(Context):
        async def elicit(self, *args, **kwargs):
            from fastmcp import ElicitationResult
            return ElicitationResult("decline", False)

    result = asyncio.run(
        write_tools.update_inventory(
            part_id=1,
            action="decrease",
            quantity=10,
            reason="Sold out",
            user_id=7,
            ctx=DecliningContext(),
        )
    )

    assert result["success"] is False
    assert conn.commit_calls == 0