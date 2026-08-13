"""
planning_eval/harness.py

Issue 7. Runs the vendored/adapted algorithms against planning_eval's
fixed scenarios (scenarios.py) with planning_eval.metrics.InstrumentedLLM
so every comparison-table cell is a real measurement of that specific
run -- not an estimate. Every function here calls straight into existing
planning/ code (fulfillment_decomposition, fulfillment_planning,
self_correction, grounded_environment) or the vendored algorithms
directly; nothing here reimplements any algorithm.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from planning.fulfillment_decomposition import build_plan_first, dynamic_fulfillment, execute_plan_first
from planning.fulfillment_planning import decide_with_lats, select_best_alternative
from planning.grounded_environment import GroundedFulfillmentEnvironment
from planning.self_correction import decide_with_reflexion, refine_customer_notification
from planning.vendor.planning_lab.algorithms.environment import Environment
from planning.vendor.planning_lab.algorithms.plan_and_solve import plan_and_solve

from planning_eval.fake_db import patched_db
from planning_eval.metrics import InstrumentedLLM
from planning_eval.scenarios import Scenario


@dataclass
class Row:
    """One comparison-table row -- the ONLY thing run_eval.py renders,
    so every field here is a real value read off an actual run, never a
    guess."""

    concern: str
    case: str
    method: str
    success: bool
    llm_calls: int
    tool_calls: int
    total_tokens: int
    token_source: str
    latency_seconds: float
    output: str  # raw decision/result text, for downstream use
    detail: str  # short display string for the table
    trace: dict[str, Any] = field(default_factory=dict)


def _no_delay(text: str) -> bool:
    return "delay" not in text.lower()


# ---------------------------------------------------------------------
# Concern 1: decomposition-first vs dynamic decomposition
# ---------------------------------------------------------------------


def run_decomposition_case(scenario: Scenario) -> list[Row]:
    rows: list[Row] = []
    with patched_db(scenario.parts, scenario.alternatives):
        llm = InstrumentedLLM()
        start = time.perf_counter()
        plan = build_plan_first(scenario.job)
        outputs, telemetry = execute_plan_first(plan, scenario.job, llm)
        wall = time.perf_counter() - start
        decision_text = outputs.get("decide", "")
        rows.append(
            Row(
                concern="decomposition",
                case=scenario.id,
                method="decomposition-first",
                success=_no_delay(decision_text),
                llm_calls=llm.log.calls,
                tool_calls=telemetry.tool_calls,
                total_tokens=llm.log.total_tokens,
                token_source=llm.log.token_source,
                latency_seconds=wall,
                output=decision_text,
                detail=decision_text[:150],
                trace={"plan": [t.id for t in plan.tasks], "outputs": outputs, "tool_call_log": telemetry.tool_call_log},
            )
        )

    with patched_db(scenario.parts, scenario.alternatives):
        llm = InstrumentedLLM()
        start = time.perf_counter()
        history, telemetry = dynamic_fulfillment(scenario.job, llm)
        wall = time.perf_counter() - start
        decision_text = history[-1][1] if history else ""
        rows.append(
            Row(
                concern="decomposition",
                case=scenario.id,
                method="dynamic-decomposition",
                success=_no_delay(decision_text),
                llm_calls=llm.log.calls,
                tool_calls=telemetry.tool_calls,
                total_tokens=llm.log.total_tokens,
                token_source=llm.log.token_source,
                latency_seconds=wall,
                output=decision_text,
                detail=decision_text[:150],
                trace={"history": history, "tool_call_log": telemetry.tool_call_log},
            )
        )
    return rows


# ---------------------------------------------------------------------
# Concern 2: Plan-and-Solve vs Tree of Thoughts (the alternative-choice
# sub-task routing.py actually routes to ToT, per num_alternatives > 1)
# ---------------------------------------------------------------------


def run_lookahead_case(scenario: Scenario) -> list[Row]:
    rows: list[Row] = []
    part = scenario.job.required_parts[0]
    part_id = scenario.parts[part][0]
    alt_names = [name for (name,) in scenario.alternatives[part_id]]
    alternatives = [(name, scenario.parts[name][2]) for name in alt_names]
    options_text = ", ".join(f"{name} (qty={qty})" for name, qty in alternatives)

    # Plan-and-Solve: one direct pass, no explicit comparison step.
    llm = InstrumentedLLM()
    start = time.perf_counter()
    question = f"Choose the best in-stock alternative for {part!r} among: {options_text}. Prefer higher quantity."
    ps_result = plan_and_solve(question, llm)
    wall = time.perf_counter() - start
    rows.append(
        Row(
            concern="planning-algorithm",
            case=scenario.id,
            method="plan-and-solve",
            success="Heavy Duty" in ps_result,
            llm_calls=llm.log.calls,
            tool_calls=0,
            total_tokens=llm.log.total_tokens,
            token_source=llm.log.token_source,
            latency_seconds=wall,
            output=ps_result,
            detail=ps_result[:150],
            trace={"question": question, "result": ps_result},
        )
    )

    # Tree of Thoughts: routing.py's own selection, generate + evaluate
    # + keep-the-best over both real candidates.
    llm = InstrumentedLLM()
    start = time.perf_counter()
    thought = select_best_alternative(part, alternatives, llm)
    wall = time.perf_counter() - start
    rows.append(
        Row(
            concern="planning-algorithm",
            case=scenario.id,
            method="tree-of-thoughts",
            success="Heavy Duty" in thought.state,
            llm_calls=llm.log.calls,
            tool_calls=0,
            total_tokens=llm.log.total_tokens,
            token_source=llm.log.token_source,
            latency_seconds=wall,
            output=thought.state,
            detail=f"{thought.state} (score={thought.score})",
            trace={"state": thought.state, "score": thought.score, "rationale": thought.rationale},
        )
    )
    return rows


# ---------------------------------------------------------------------
# Concern 3: LATS ungrounded vs grounded, on the same fabricated-
# alternative finding
# ---------------------------------------------------------------------


def run_lats_grounding_case(scenario: Scenario, findings: str) -> list[Row]:
    rows: list[Row] = []
    with patched_db(scenario.parts, scenario.alternatives):
        for label, environment in (
            ("lats-ungrounded", Environment(success_threshold=0.6, rng=random.Random(42))),
            ("lats-grounded", GroundedFulfillmentEnvironment(scenario.job)),
        ):
            llm = InstrumentedLLM()
            start = time.perf_counter()
            result = decide_with_lats(scenario.job, findings, llm, environment=environment)
            wall = time.perf_counter() - start
            fabricated_accepted = result.success and "Racing Edition" in result.output
            rows.append(
                Row(
                    concern="grounding",
                    case=scenario.id,
                    method=label,
                    success=result.success,
                    llm_calls=llm.log.calls,
                    tool_calls=getattr(environment, "tool_calls", 0),
                    total_tokens=llm.log.total_tokens,
                    token_source=llm.log.token_source,
                    latency_seconds=wall,
                    output=result.output,
                    detail=f"best_score={result.best_score} fabricated_accepted={fabricated_accepted}",
                    trace={"output": result.output, "best_score": result.best_score, "iterations": result.iterations},
                )
            )
    return rows


# ---------------------------------------------------------------------
# Concern 4: Reflexion -- a single trial vs cross-trial memory
# ---------------------------------------------------------------------


def run_reflexion_case(scenario: Scenario, findings: str) -> list[Row]:
    rows: list[Row] = []
    with patched_db(scenario.parts, scenario.alternatives):
        for label, max_trials in (("single-retry (max_trials=1)", 1), ("reflexion (max_trials=3)", 3)):
            llm = InstrumentedLLM()
            start = time.perf_counter()
            result = decide_with_reflexion(scenario.job, findings, llm, max_trials=max_trials)
            wall = time.perf_counter() - start
            rows.append(
                Row(
                    concern="self-correction",
                    case=scenario.id,
                    method=label,
                    success=result.success,
                    llm_calls=llm.log.calls,
                    tool_calls=0,  # grounding tool calls counted inside GroundedFulfillmentEnvironment
                    total_tokens=llm.log.total_tokens,
                    token_source=llm.log.token_source,
                    latency_seconds=wall,
                    output=result.output,
                    detail=f"trials={len(result.trials)}",
                    trace={
                        "trials": [
                            {
                                "number": t.number,
                                "attempt": t.attempt,
                                "success": t.feedback.success,
                                "reflection": t.reflection,
                            }
                            for t in result.trials
                        ],
                        "memory": result.memory,
                    },
                )
            )
    return rows


# ---------------------------------------------------------------------
# Concern 5: Self-Refine, on the cheap notification sub-task
# ---------------------------------------------------------------------


def run_self_refine_case(scenario: Scenario, decision_text: str) -> Row:
    with patched_db(scenario.parts, scenario.alternatives):
        llm = InstrumentedLLM()
        start = time.perf_counter()
        result = refine_customer_notification(scenario.job, decision_text, llm)
        wall = time.perf_counter() - start
        return Row(
            concern="self-correction",
            case=scenario.id,
            method="self-refine (notification)",
            success=bool(result.revised),
            llm_calls=llm.log.calls,
            tool_calls=0,
            total_tokens=llm.log.total_tokens,
            token_source=llm.log.token_source,
            latency_seconds=wall,
            output=result.revised,
            detail=f"revised != draft: {result.revised != result.draft}",
            trace={"draft": result.draft, "critique": result.critique, "revised": result.revised},
        )


__all__ = [
    "Row",
    "run_decomposition_case",
    "run_lats_grounding_case",
    "run_lookahead_case",
    "run_reflexion_case",
    "run_self_refine_case",
]
