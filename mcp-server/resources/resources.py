"""
Resources (Protocol Concern: Resources)

The warehouse & inventory policy is static reference material the model
should read once and reason over -- not a function it calls with
arguments -- so it's exposed via resources/list + resources/read rather
than wrapped as a tool.
"""

from pathlib import Path

from app import mcp

_POLICY_PATH = Path(__file__).parent / "company_policy.md"


@mcp.resource("warehouse://policy/inventory")
def inventory_policy() -> str:
    """
    Auto Care's warehouse & inventory policy: stock thresholds, who is
    authorized to change inventory, the elicitation trigger conditions,
    and the audit-trail requirement for every stock change.
    """
    return _POLICY_PATH.read_text(encoding="utf-8")