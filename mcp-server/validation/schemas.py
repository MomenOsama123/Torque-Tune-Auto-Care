"""JSON Schema definitions for inventory tools."""

UPDATE_INVENTORY_SCHEMA = {
    "name": "update_inventory",
    "description": (
        "Adjust the stock quantity of a spare part. Manager role required. "
        "Large decreases or decreases that would zero out stock require "
        "human confirmation via elicitation before they are applied."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "part_id": {
                "type": "integer",
                "minimum": 1,
                "description": "ID of the spare part in the SpareParts table.",
            },
            "action": {
                "type": "string",
                "enum": ["increase", "decrease", "set"],
                "description": "Whether to increase, decrease, or set the absolute quantity.",
            },
            "quantity": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "For increase/decrease: the amount to change by (must be positive). "
                    "For set: the new absolute quantity (must be >= 0)."
                ),
            },
            "reason": {
                "type": "string",
                "minLength": 5,
                "maxLength": 300,
                "description": "Human-readable reason for the change, stored in InventoryLogs.",
            },
            "user_id": {
                "type": "integer",
                "minimum": 1,
                "description": "ID of the user performing the change, used for the authorization check.",
            },
        },
        "required": ["part_id", "action", "quantity", "reason", "user_id"],
        "additionalProperties": False,
    },
}
