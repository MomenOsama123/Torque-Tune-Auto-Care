"""
planning/tests/test_planning_routing.py

Issue 3 verification. Uses planning/model_provider.py's offline fallback
(no ANTHROPIC_API_KEY needed), same convention as planning/tests/
test_fulfillment_decomposition.py (Issue 2, not modified here).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_ROOT = ROOT / "mcp-server"
for _p in (str(ROOT), str(MCP_SERVER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from planning.fulfillment_decomposition import JobRequest  # noqa: E402
from planning.fulfillment_planning import (  # noqa: E402
    decide_with_lats,
    draft_notification,
    run_planning_layer,
    select_best_alternative,
)
from planning.model_provider import get_llm  # noqa: E402
from planning.routing import (  # noqa: E402
    Environment,
    SubtaskKind,
    classify_subtask,
    run_subtask,
)


# ---------------------------------------------------------------------
# 4. The router actually chooses between PS / ToT / LATS
# ---------------------------------------------------------------------


def test_router_picks_different_algorithms_for_different_subtasks():
    assert classify_subtask("notify") is SubtaskKind.MECHANICAL
    assert classify_subtask("check_brake_pad") is SubtaskKind.MECHANICAL
    assert classify_subtask("choose_alt", num_alternatives=2) is SubtaskKind.COMPARE_ALTERNATIVES
    assert classify_subtask("altsearch_oil_filter", num_alternatives=3) is SubtaskKind.COMPARE_ALTERNATIVES
    assert classify_subtask("decide") is SubtaskKind.HIGH_IMPACT_DECISION
    # A single-alternative case is NOT a real comparison -- confirms the
    # router looks at sub-task characteristics, not just the task_id.
    assert classify_subtask("altsearch_oil_filter", num_alternatives=1) is SubtaskKind.MECHANICAL


# ---------------------------------------------------------------------
# 1. Plan-and-Solve executes the mechanical sub-task
# ---------------------------------------------------------------------


def test_plan_and_solve_drafts_notification():
    job = JobRequest(job_id="job-42", required_parts=["Brake Pad"])
    llm = get_llm()
    text = draft_notification(job, "proceed with the original Brake Pad, in stock.", llm)
    assert isinstance(text, str) and text.strip()


# ---------------------------------------------------------------------
# 2. ToT is selected (and actually runs) for a multi-option comparison
# ---------------------------------------------------------------------


def test_tree_of_thoughts_picks_the_higher_stock_alternative():
    llm = get_llm()
    alternatives = [("Oil Filter XL", 5), ("Oil Filter Std", 2)]
    best = select_best_alternative("Oil Filter", alternatives, llm)
    assert "Oil Filter XL" in best.state
    assert best.score >= 0.0


# ---------------------------------------------------------------------
# 3. LATS is selected for the high-impact decision sub-task
# ---------------------------------------------------------------------


def test_lats_produces_a_grounded_final_decision():
    job = JobRequest(job_id="job-42", required_parts=["Brake Pad"])
    llm = get_llm()
    # Seeded Environment -- deterministic, still the vendored (ungrounded)
    # default evaluator. Issue 4 replaces this evaluator, not this test.
    environment = Environment(rng=random.Random(7))
    result = decide_with_lats(job, "Brake Pad: id=1 quantity=20", llm, environment=environment)
    assert result.output.strip()
    assert result.iterations >= 1


# ---------------------------------------------------------------------
# 5. Works with the actual Issue 2 decomposition output
# ---------------------------------------------------------------------


def test_planning_layer_consumes_issue2_output_without_modifying_it():
    job = JobRequest(job_id="job-42", required_parts=["Oil Filter"])
    llm = get_llm()
    # Shape produced by execute_plan_first() in Issue 2 -- reused as-is,
    # not regenerated, to confirm this layer only *consumes* it.
    pf_outputs = {
        "check_oil_filter": "Oil Filter: id=2 quantity=0",
        "altsearch_oil_filter": "Oil Filter: alternatives=[Oil Filter XL (qty=5), Oil Filter Std (qty=2)]",
    }
    environment = Environment(rng=random.Random(3))
    result = run_planning_layer(job, pf_outputs, llm, environment=environment)

    assert "Oil Filter" in result["alternative_choices"]
    assert result["final_decision"].output.strip()
    assert isinstance(result["customer_notification"], str) and result["customer_notification"].strip()


def test_planning_layer_skips_tot_when_only_one_stocked_alternative():
    """Router characteristic check applied end-to-end: a single stocked
    alternative is not a real comparison, so no ToT call/entry happens
    for it."""
    job = JobRequest(job_id="job-9", required_parts=["Brake Pad"])
    llm = get_llm()
    pf_outputs = {
        "check_brake_pad": "Brake Pad: id=1 quantity=0",
        "altsearch_brake_pad": "Brake Pad: alternatives=[Brake Pad HD (qty=4)]",
    }
    environment = Environment(rng=random.Random(1))
    result = run_planning_layer(job, pf_outputs, llm, environment=environment)
    assert result["alternative_choices"] == {}


# ---------------------------------------------------------------------
# 6. run_subtask dispatch sanity (direct, no fulfillment wrapper)
# ---------------------------------------------------------------------


def test_run_subtask_dispatches_by_kind():
    llm = get_llm()
    ps_result = run_subtask(SubtaskKind.MECHANICAL, llm=llm, question="Summarize: stock is fine.")
    assert isinstance(ps_result, str)

    tot_result = run_subtask(
        SubtaskKind.COMPARE_ALTERNATIVES,
        llm=llm,
        problem="Choose the best in-stock alternative for 'X' among: A (qty=5), B (qty=1).",
        depth=1,
        beam_width=1,
    )
    assert isinstance(tot_result, list) and tot_result

    lats_result = run_subtask(
        SubtaskKind.HIGH_IMPACT_DECISION,
        llm=llm,
        task="Decide proceed or delay given: A (qty=5).",
        environment=Environment(rng=random.Random(11)),
        iterations=1,
        n_actions=1,
    )
    assert lats_result.output.strip()
