def build_inventory_confirmation(
    part_id: int,
    old_quantity: int,
    new_quantity: int
):
    """
    Build confirmation data for a risky inventory update.
    """

    return {
        "part_id": part_id,
        "old_quantity": old_quantity,
        "new_quantity": new_quantity,
        "message": (
            f"Inventory for part {part_id} will change "
            f"from {old_quantity} to {new_quantity}. "
            "This is a potentially risky inventory change. "
            "Do you want to continue?"
        )
    }