"""
Defensive Tool Design for update_inventory.

Server-side validation and authorization, independent of the JSON Schema
in schemas.py. Never trust that a well-formed request is a legitimate one.
"""

from dataclasses import dataclass
from typing import Literal, Optional

Action = Literal["increase", "decrease", "set"]


class ValidationError(Exception):
    """Raised when the request fails a server-side business rule."""


class AuthorizationError(Exception):
    """Raised when the acting user is not permitted to perform this action."""


@dataclass
class ElicitationRequired:
    """Signals the handler must call elicitation/create before applying the change."""
    reason: str
    proposed_old_quantity: int
    proposed_new_quantity: int


def authorize_update_inventory(user_role: str) -> None:
    """Handler-level authorization check, independent of the schema."""
    normalized_role = user_role.lower()
    if normalized_role not in {"manager", "admin"}:
        raise AuthorizationError(
            "Only users with role 'manager' or 'admin' may call update_inventory. "
            f"Caller has role '{user_role}'."
        )


def compute_new_quantity(action: Action, quantity: int, current_quantity: int) -> int:
    """
    Pure arithmetic for the resulting quantity. Shared by validate_update_inventory
    and the handler, so the handler never has to re-derive this on its own.
    """
    if action == "set":
        if quantity < 0:
            raise ValidationError("Quantity cannot be set to a negative value.")
        return quantity
    elif action == "increase":
        return current_quantity + quantity
    elif action == "decrease":
        new_quantity = current_quantity - quantity
        if new_quantity < 0:
            raise ValidationError(
                f"Cannot decrease by {quantity}: only {current_quantity} in stock."
            )
        return new_quantity
    else:
        raise ValidationError(f"Unknown action '{action}'.")


def validate_update_inventory(
    action: Action,
    quantity: int,
    current_quantity: int,
    part_status: str,
    reason: str,
) -> Optional[ElicitationRequired]:
    """
    Returns ElicitationRequired if the handler must pause for human
    confirmation, or None if the change may proceed immediately.
    """
    if part_status == "discontinued":
        raise ValidationError(
            "This part is discontinued; inventory can no longer be adjusted."
        )

    if not reason or not reason.strip():
        raise ValidationError("A non-empty reason is required for every inventory change.")

    new_quantity = compute_new_quantity(action, quantity, current_quantity)

    if new_quantity == 0 and current_quantity > 0:
        return ElicitationRequired(
            reason="This change will bring stock to zero. Confirm before applying.",
            proposed_old_quantity=current_quantity,
            proposed_new_quantity=new_quantity,
        )

    if action == "decrease" and quantity > 20:
        return ElicitationRequired(
            reason=(
                f"This is a decrease of {quantity} units in a single call, "
                "treated as a probable data-entry error until confirmed."
            ),
            proposed_old_quantity=current_quantity,
            proposed_new_quantity=new_quantity,
        )

    return None