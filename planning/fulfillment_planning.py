"""
planning/fulfillment_planning.py

Issue 3: wires the router (planning/routing.py) into the real spare-parts
workflow, consuming Issue 2's decomposition output
(planning/fulfillment_decomposition.py -- NOT modified here) rather than
re-decomposing anything.

Three concrete sub-tasks in this workflow actually need an LLM call (Issue
2's tool-call nodes -- check_stock/search_spare_part/suggest_alternative --
stay untouched, real DB calls, no LLM):
  1. Choosing the best in-stock alternative, when Issue 2's altsearch_*
     step found more than one -> COMPARE_ALTERNATIVES -> Tree of Thoughts
  2. The final proceed/delay recommendation -> HIGH_IMPACT_DECISION -> LATS
  3. Drafting the customer-facing update once a decision exists ->
     MECHANICAL -> Plan-and-Solve

environment=None now defaults to Issue 4's grounded evaluator
(planning/grounded_environment.GroundedFulfillmentEnvironment), which
checks a candidate proceed/delay decision against the real Torque Tune
database instead of the vendored toolkit's randomized default. Callers
that pass their own `environment` (e.g. the Issue 3 tests, which seed the
vendored ungrounded Environment on purpose) are unaffected -- this file's
routing/algorithm wiring itself is unchanged.
"""

from __future__ import annotations

import re

from planning.fulfillment_decomposition import JobRequest
from planning.grounded_environment import GroundedFulfillmentEnvironment
from planning.routing import (
    Environment,
    LATSResult,
    SubtaskKind,
    Thought,
    classify_subtask,
    run_subtask,
)


def _parse_stocked_alternatives(altsearch_output: str) -> list[tuple[str, int]]:
    """Parses Issue 2's own output text, e.g.
    "Oil Filter: alternatives=[Oil Filter XL (qty=5), Oil Filter Std (qty=2)]"
    Only alternatives with qty > 0 count as usable candidates to compare."""
    pairs = re.findall(r"([\w][\w ]*?) \(qty=(\d+)\)", altsearch_output)
    return [(name.strip(), int(qty)) for name, qty in pairs if int(qty) > 0]


def select_best_alternative(part: str, alternatives: list[tuple[str, int]], llm) -> Thought:
    """Routed through Tree of Thoughts -- only called when there are 2+
    stocked alternatives to actually compare (see run_planning_layer)."""
    kind = classify_subtask("choose_alt", num_alternatives=len(alternatives))
    assert kind is SubtaskKind.COMPARE_ALTERNATIVES
    options = ", ".join(f"{name} (qty={qty})" for name, qty in alternatives)
    problem = (
        f"Choose the best in-stock alternative for {part!r} among: {options}. "
        "Prefer higher quantity; a name closer to the original part implies better "
        "compatibility. There is no supplier-availability tool in this system -- "
        "never propose checking one."
    )
    thoughts = run_subtask(kind, llm=llm, problem=problem, depth=1, beam_width=1)
    return thoughts[0] if thoughts else Thought(state=f"no candidate for {part}", score=0.0)


def decide_with_lats(
    job: JobRequest,
    findings_summary: str,
    llm,
    environment: "Environment | GroundedFulfillmentEnvironment | None" = None,
    iterations: int = 2,
    n_actions: int = 2,
) -> LATSResult:
    """Routed through LATS -- the final proceed/delay call, the one node
    in this workflow where a wrong decision has real cost (reserved-but-
    unusable inventory, an incompatible substitute, an unmet promise).
    Defaults to Issue 4's grounded environment, scoped to this job's real
    required parts/alternatives."""
    kind = classify_subtask("decide")
    assert kind is SubtaskKind.HIGH_IMPACT_DECISION
    environment = environment or GroundedFulfillmentEnvironment(job)
    task = (
        f"Job {job.job_id}: decide proceed-with-part, proceed-with-alternative, or "
        f"delay, and write the full recommendation as the candidate state. "
        f"Findings:\n{findings_summary}\n"
        "There is no supplier-availability tool in this system -- never propose "
        "checking one; delay is the correct answer when nothing is in stock."
    )
    return run_subtask(kind, llm=llm, task=task, environment=environment, iterations=iterations, n_actions=n_actions)


def draft_notification(job: JobRequest, decision_text: str, llm) -> str:
    """Routed through Plan-and-Solve -- one deterministic pass, no
    branching needed once a decision already exists."""
    kind = classify_subtask("notify")
    assert kind is SubtaskKind.MECHANICAL
    question = (
        f"Write a short customer-facing update for job {job.job_id} given this "
        f"decision:\n{decision_text}\nKeep it to 2-3 sentences, plain language, no "
        "internal part IDs."
    )
    return run_subtask(kind, llm=llm, question=question)


def run_planning_layer(
    job: JobRequest,
    pf_outputs: dict[str, str],
    llm,
    environment: "Environment | GroundedFulfillmentEnvironment | None" = None,
) -> dict:
    """Consumes Issue 2's execute_plan_first() output directly (does not
    call or re-run any Issue 2 function). For every altsearch_* node that
    found 2+ stocked alternatives, routes the choice through ToT. Always
    routes the final decision through LATS and the resulting customer
    update through Plan-and-Solve."""
    findings_summary = "\n".join(v for k, v in pf_outputs.items() if k != "decide")
    # Same slug convention as fulfillment_decomposition.py's part_by_slug,
    # so a part like "Oil Filter" round-trips through "altsearch_oil_filter"
    # back to its original casing instead of staying lowercased.
    part_by_slug = {p.lower().replace(" ", "_"): p for p in job.required_parts}

    alternative_choices: dict[str, Thought] = {}
    for task_id, output in pf_outputs.items():
        if not task_id.startswith("altsearch_"):
            continue
        stocked = _parse_stocked_alternatives(output)
        if len(stocked) > 1:
            slug = task_id[len("altsearch_"):]
            part = part_by_slug.get(slug, slug.replace("_", " "))
            alternative_choices[part] = select_best_alternative(part, stocked, llm)

    lats_result = decide_with_lats(job, findings_summary, llm, environment=environment)
    notification = draft_notification(job, lats_result.output, llm)

    return {
        "alternative_choices": alternative_choices,
        "final_decision": lats_result,
        "customer_notification": notification,
    }
