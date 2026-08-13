try:
    from mcp.server.fastmcp import FastMCP, Context
except ImportError:
    from fastmcp import FastMCP, Context

from app import mcp
# Import the global memory manager
from app import memory_manager

from databases.db import get_connection
from auth.authorization import require_manager
# from validation.schemas import SearchKnowledgeBaseInput
from validation.validators import (
    authorize_update_inventory,
    validate_update_inventory,
    compute_new_quantity,
    ElicitationRequired,
    ValidationError,
    AuthorizationError,
)
from elicitation.elicitation import build_inventory_confirmation

from notifications import (
    inventory_updated,
    spare_part_added,
    spare_part_deleted,
)

from progress import report_inventory_progress
# from option_b_memory_example import load_memory_context, maybe_remember

# -----------------------------
# Helper Functions
# -----------------------------

def _ensure_non_negative(quantity: int):
    if quantity < 0:
        raise ValueError("Quantity cannot be negative.")


def _part_exists(cursor, part_id: int) -> bool:
    cursor.execute(
        "SELECT 1 FROM SpareParts WHERE id = ?",
        (part_id,)
    )
    return cursor.fetchone() is not None


# -----------------------------
# Update Inventory
# -----------------------------

@mcp.tool()
async def update_inventory(
    part_id: int,
    action: str,
    quantity: int,
    reason: str,
    user_id: int,
    ctx: Context,
):
    """
    Adjust the stock quantity of a spare part. Manager role required.
    Large decreases or decreases that would zero out stock require
    human confirmation via elicitation before they are applied.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Authorization happens in the handler, against the role the server
        # looks up for user_id — never against a role the caller merely claims.
        cursor.execute("SELECT role FROM Users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row is None:
            raise AuthorizationError(f"User {user_id} not found.")
        authorize_update_inventory(user_row[0])

        cursor.execute(
            "SELECT quantity, status FROM SpareParts WHERE id = ?",
            (part_id,)
        )
        part_row = cursor.fetchone()
        if part_row is None:
            raise ValueError("Spare part not found.")

        current_quantity, part_status = part_row

        outcome = validate_update_inventory(
            action=action,
            quantity=quantity,
            current_quantity=current_quantity,
            part_status=part_status,
            reason=reason,
        )

        if isinstance(outcome, ElicitationRequired):
            confirmation = build_inventory_confirmation(
                part_id=part_id,
                old_quantity=outcome.proposed_old_quantity,
                new_quantity=outcome.proposed_new_quantity,
            )

            response = await ctx.elicit(
                message=confirmation["message"],
                schema={
                    "type": "object",
                    "properties": {"confirm": {"type": "boolean"}},
                    "required": ["confirm"],
                },
            )

            if response.action != "accept" or not response.data:
                return {
                    "success": False,
                    "message": "Inventory change cancelled — confirmation was not granted.",
                }

            new_quantity = outcome.proposed_new_quantity
        else:
            new_quantity = compute_new_quantity(action, quantity, current_quantity)

        cursor.execute(
            "UPDATE SpareParts SET quantity = ? WHERE id = ?",
            (new_quantity, part_id)
        )

        cursor.execute(
            """
            INSERT INTO InventoryLogs
            (part_id, user_id, old_quantity, new_quantity, action, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (part_id, user_id, current_quantity, new_quantity, action, reason)
        )

        conn.commit()

        # Update the scratchpad to mark the inventory update step as complete
        memory_manager.scratchpad.complete_step(
            step="update_inventory",
            result=f"Updated part {part_id} with action {action} by {quantity}.",
            result_key=f"inventory_update_{part_id}"
        )
        
        # Save this significant event in the episodic memory
        memory_manager.episodic.add_episode(
            event_type="inventory_updated",
            content={
                "part_id": part_id,
                "action": action,
                "quantity": quantity,
                "reason": reason,
                "user_id": user_id,
                "new_quantity": new_quantity
            },
            promotion_reason="Significant stock change executed by user."
        )

        return inventory_updated(part_id, new_quantity)

    finally:
        conn.close()


# -----------------------------
# Add Spare Part
# -----------------------------

@mcp.tool()
def add_spare_part(
    part_id: int | None,
    part_name: str,
    quantity: int,
    user_role: str
):
    """
    Add a new spare part to the inventory.
    Only managers and admins are allowed.
    """

    require_manager(user_role)
    _ensure_non_negative(quantity)

    if not part_name.strip():
        raise ValueError("Part name cannot be empty.")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Insert with manually provided ID
        if part_id is not None:

            if _part_exists(cursor, part_id):
                raise ValueError("Spare part already exists.")

            cursor.execute(
                """
                INSERT INTO SpareParts
                (id, part_name, quantity)
                VALUES (?, ?, ?)
                """,
                (part_id, part_name, quantity)
            )

        # Let database generate the ID
        else:

            cursor.execute(
                """
                INSERT INTO SpareParts
                (part_name, quantity)
                VALUES (?, ?)
                """,
                (part_name, quantity)
            )

            part_id = cursor.lastrowid

        conn.commit()

        # Update scratchpad
        memory_manager.scratchpad.complete_step(
            step="add_spare_part",
            result=f"Added new part: {part_name} with quantity {quantity}.",
            result_key=f"spare_part_added_{part_id}"
        )
        
        # Add to episodic memory
        memory_manager.episodic.add_episode(
            event_type="spare_part_added",
            content={
                "part_id": part_id,
                "part_name": part_name,
                "quantity": quantity,
                "user_role": user_role
            },
            promotion_reason="New spare part added to the inventory."
        )

        return spare_part_added(
            part_id,
            part_name
        )

    finally:
        conn.close()


# -----------------------------
# Delete Spare Part
# -----------------------------

@mcp.tool()
def delete_spare_part(
    part_id: int,
    user_role: str
):
    """
    Delete a spare part from the inventory.
    Only managers and admins are allowed.
    """

    require_manager(user_role)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        if not _part_exists(cursor, part_id):
            raise ValueError("Spare part not found.")

        cursor.execute(
            """
            DELETE FROM SpareParts
            WHERE id = ?
            """,
            (part_id,)
        )

        conn.commit()

        # Update scratchpad
        memory_manager.scratchpad.complete_step(
            step="delete_spare_part",
            result=f"Deleted part ID: {part_id}.",
            result_key=f"spare_part_deleted_{part_id}"
        )
        
        # Add to episodic memory
        memory_manager.episodic.add_episode(
            event_type="spare_part_deleted",
            content={
                "part_id": part_id,
                "user_role": user_role
            },
            promotion_reason="Spare part permanently removed from the inventory."
        )

        return spare_part_deleted(part_id)

    finally:
        conn.close()


# -----------------------------
# Generate Inventory Report
# -----------------------------

@mcp.tool()
async def generate_inventory_report(ctx: Context):
    """
    Generate a summary report for the spare parts inventory
    while reporting progress to the client.
    """

    await report_inventory_progress(ctx, 0)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Step 1: Read inventory
        await report_inventory_progress(ctx, 25)

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_parts,
                COALESCE(SUM(quantity), 0) AS total_quantity,
                COALESCE(AVG(price), 0) AS average_price
            FROM SpareParts
            """
        )

        report = cursor.fetchone()

        # Step 2: Calculate report
        await report_inventory_progress(ctx, 50)

        total_parts = report[0]
        total_quantity = report[1]
        average_price = round(report[2], 2)

        # Step 3: Prepare report
        await report_inventory_progress(ctx, 75)

        result = {
            "success": True,
            "total_parts": total_parts,
            "total_quantity": total_quantity,
            "average_price": average_price
        }        
        # Completed
        await report_inventory_progress(ctx, 100)

        # Update scratchpad
        memory_manager.scratchpad.complete_step(
            step="generate_inventory_report",
            result="Inventory report generated successfully.",
            result_key="latest_inventory_report"
        )
        
        # Add to episodic memory
        memory_manager.episodic.add_episode(
            event_type="inventory_report_generated",
            content=result,
            promotion_reason="User requested a full inventory summary report."
        )

        return result

    finally:
        conn.close()
        
        

# def handle_user_message(user_message: str, entity_id: str):
#     # Load relevant past memories for this entity
#     memory_context = load_memory_context(entity_id, user_message)

#     # Build prompt with memory
#     prompt = f"""
#     Previous relevant notes:
#     {memory_context}

#     User message:
#     {user_message}
#     """

#     # Generate reply from your agent/model
#     reply = generate_reply(prompt)

#     # Save important facts for future sessions
#     maybe_remember(user_message, entity_id)

#     return reply