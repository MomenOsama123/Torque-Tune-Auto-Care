"""
planning/self_correction.py

Issue 5: the two vendored self-correction algorithms (planning/vendor/
planning_lab/algorithms/{self_refine,reflexion}.py, unmodified), wired
into the real spare-parts fulfillment workflow -- NOT into
planning/routing.py, which Issue 3's own docstring scopes to "which of
the three vendored PLANNING algorithms (PS/ToT/LATS) handles a given
sub-task". Self-Refine and Reflexion are a different family (revise an
existing output vs. search for one) and are wired here instead, in a new
file, so Issue 3/4's files stay untouched (Issue 1's "build on top, don't
rewrite" constraint).

Mapping, applied to the actual workflow:
  - Cheap sub-task, one existing draft to improve, no real cost to
    re-running it: the customer-facing notification
    (planning/fulfillment_planning.draft_notification, Issue 3's
    Plan-and-Solve output) -> Self-Refine. One critique-then-revise pass,
    critiqued by REAL deterministic checks (word count, goal-term
    overlap, visible structure -- planning_lab's own
    deterministic_checks(), not an LLM opinion) plus an independent LLM
    critique, exactly as the vendored self_refine.py already does.
  - High-impact sub-task where a single wrong guess is expensive and
    multiple attempts within the same run can genuinely learn from each
    other: the final proceed/alternative/delay decision -> Reflexion,
    using Issue 4's GroundedFulfillmentEnvironment (same default
    convention as fulfillment_planning.decide_with_lats) as the real,
    non-LLM pass/fail signal each trial is judged against. This is an
    ADDITIONAL technique for the same decision LATS already handles
    (Issue 3) -- multi-trial episodic self-correction is a different
    approach to that decision, not a replacement for the tree search;
    both are available so Issue 7's evaluation harness can compare them
    head to head, per the plan's own "Reflexion vs LATS" framing.

Grounding source for Reflexion: the SAME real MCP tool implementations
and database seam Issue 4 already uses (via
GroundedFulfillmentEnvironment) -- no new tool, table, or concept
invented here. See planning/tests/test_self_correction.py for a
deterministic demonstration of a failed trial's reflection changing the
next trial's outcome (Issue 5 requirement 3).
"""

from __future__ import annotations

from planning.fulfillment_decomposition import JobRequest
from planning.fulfillment_planning import draft_notification
from planning.grounded_environment import GroundedFulfillmentEnvironment
from planning.routing import Environment
from planning.vendor.planning_lab.algorithms.reflexion import (
    ReflexionResult,
    reflexion,
)
from planning.vendor.planning_lab.algorithms.self_refine import (
    ReflectionResult,
    reflect_and_refine,
)


def refine_customer_notification(job: JobRequest, decision_text: str, llm) -> ReflectionResult:
    """Self-Refine, applied to the one genuinely cheap sub-task in this
    workflow: the customer-facing update. Reuses Issue 3's
    draft_notification() (Plan-and-Solve) to produce the first-pass
    draft -- this function does not duplicate that prompt -- then runs
    the vendored reflect_and_refine() unmodified on top of it. Cheap to
    re-run because it's a few sentences of prose with no external side
    effect, unlike the decision itself."""
    draft = draft_notification(job, decision_text, llm)
    goal = (
        f"A short, plain-language customer-facing update for job {job.job_id} "
        f"about this decision: {decision_text}"
    )
    return reflect_and_refine(goal, draft, llm)


def decide_with_reflexion(
    job: JobRequest,
    findings_summary: str,
    llm,
    environment: "Environment | GroundedFulfillmentEnvironment | None" = None,
    max_trials: int = 3,
    memory_size: int = 3,
) -> ReflexionResult:
    """Reflexion, applied to the final proceed/alternative/delay
    decision -- same task framing as
    fulfillment_planning.decide_with_lats (deliberately worded the same
    way, for a fair Issue 7 comparison), same grounded environment
    default. Each failed trial's reflection is real episodic memory
    (vendored reflexion()'s own `memory` list, capped at `memory_size`)
    fed verbatim into the next trial's prompt -- not summarized or
    discarded between trials."""
    environment = environment or GroundedFulfillmentEnvironment(job)
    task = (
        f"Job {job.job_id}: decide proceed-with-part, proceed-with-alternative, or "
        f"delay, and write the full recommendation as the candidate state. "
        f"Findings:\n{findings_summary}\n"
        "There is no supplier-availability tool in this system -- never propose "
        "checking one; delay is the correct answer when nothing is in stock."
    )
    return reflexion(task, llm, environment, max_trials=max_trials, memory_size=memory_size)


__all__ = [
    "ReflectionResult",
    "ReflexionResult",
    "decide_with_reflexion",
    "refine_customer_notification",
]
