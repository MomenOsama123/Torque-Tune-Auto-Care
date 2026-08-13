"""
planning/routing.py

Issue 3: the ONE routing component. Decides which of the three vendored
planning algorithms (planning/vendor/planning_lab/algorithms/{plan_and_solve,
tree_of_thoughts,lats}.py, unmodified) handles a given sub-task from the
real spare-parts fulfillment workflow (planning/fulfillment_decomposition.py,
Issue 2).

Mapping, applied to the actual workflow:
  - MECHANICAL sub-task ("draft the customer notification" -- one
    deterministic pass, no branching) -> Plan-and-Solve
  - COMPARE_ALTERNATIVES sub-task ("pick the best in-stock alternative
    part when Issue 2's altsearch step found more than one") -> Tree of
    Thoughts
  - HIGH_IMPACT_DECISION sub-task ("decide" -- final proceed/delay call;
    wrong answer costs a reserved-but-unusable part, an incompatible
    substitute, or an unmet promise) -> LATS, with the vendored toolkit's
    default (ungrounded) Environment -- Issue 4 replaces that evaluator,
    not this routing.
"""

from __future__ import annotations

from enum import Enum

from planning.vendor.planning_lab.algorithms.environment import Environment
from planning.vendor.planning_lab.algorithms.lats import LATSResult, lats
from planning.vendor.planning_lab.algorithms.plan_and_solve import plan_and_solve
from planning.vendor.planning_lab.algorithms.tree_of_thoughts import tree_of_thoughts
from planning.vendor.planning_lab.models import Thought


class SubtaskKind(str, Enum):
    MECHANICAL = "mechanical"
    COMPARE_ALTERNATIVES = "compare_alternatives"
    HIGH_IMPACT_DECISION = "high_impact_decision"


ALGORITHM_FOR_KIND: dict[SubtaskKind, str] = {
    SubtaskKind.MECHANICAL: "plan_and_solve",
    SubtaskKind.COMPARE_ALTERNATIVES: "tree_of_thoughts",
    SubtaskKind.HIGH_IMPACT_DECISION: "lats",
}


def classify_subtask(task_id: str, *, num_alternatives: int = 0) -> SubtaskKind:
    """Real routing logic based on the actual Issue 2 task shapes.

    task_id == "decide"                         -> HIGH_IMPACT_DECISION
    task_id starts with "choose_alt" OR
        num_alternatives > 1 (2+ stocked
        alternatives from an altsearch_* node)   -> COMPARE_ALTERNATIVES
    everything else (e.g. "notify")              -> MECHANICAL
    """
    if task_id == "decide":
        return SubtaskKind.HIGH_IMPACT_DECISION
    if task_id.startswith("choose_alt") or num_alternatives > 1:
        return SubtaskKind.COMPARE_ALTERNATIVES
    return SubtaskKind.MECHANICAL


def run_subtask(kind: SubtaskKind, *, llm, **kwargs):
    """Dispatches to the vendored algorithm the router selected. kwargs
    differ per kind -- callers use classify_subtask() first, then pass
    exactly what that algorithm needs:
      MECHANICAL           -> question: str
      COMPARE_ALTERNATIVES -> problem: str, depth: int = 2, beam_width: int = 2
      HIGH_IMPACT_DECISION -> task: str, environment: Environment,
                               iterations: int = 2, n_actions: int = 2
    """
    if kind is SubtaskKind.MECHANICAL:
        return plan_and_solve(kwargs["question"], llm)
    if kind is SubtaskKind.COMPARE_ALTERNATIVES:
        return tree_of_thoughts(
            kwargs["problem"],
            llm,
            depth=kwargs.get("depth", 2),
            beam_width=kwargs.get("beam_width", 2),
        )
    if kind is SubtaskKind.HIGH_IMPACT_DECISION:
        return lats(
            kwargs["task"],
            llm,
            kwargs["environment"],
            iterations=kwargs.get("iterations", 2),
            n_actions=kwargs.get("n_actions", 2),
        )
    raise ValueError(f"Unrouted subtask kind: {kind}")


__all__ = [
    "ALGORITHM_FOR_KIND",
    "Environment",
    "LATSResult",
    "SubtaskKind",
    "Thought",
    "classify_subtask",
    "run_subtask",
]
