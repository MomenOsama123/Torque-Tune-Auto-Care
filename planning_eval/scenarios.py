"""
planning_eval/scenarios.py

Issue 7's fixed test suite -- kept fixed once evaluation starts (per the
lab's own guardrail: "changing test cases between runs invalidates your
comparison table"). Four real spare-parts fulfillment jobs, each built to
be the genuine, reproducible case one required comparison needs:

  1. DECOMP_FIRST_FAVORED -- decomposition-first should win (both parts
     genuinely need their alt-search branch, so the worst-case plan pays
     for nothing it didn't need, with far fewer LLM calls than dynamic's
     per-step decision loop).
  2. DYNAMIC_FAVORED -- same shape as fulfillment_demo.py's own
     divergence case, new part names: one well-stocked part, one not, so
     dynamic decomposition skips a branch decomposition-first always
     pays for.
  3. LOOKAHEAD_NEEDED -- one part with TWO stocked alternatives, so
     planning/routing.py's own classify_subtask() actually routes it to
     Tree of Thoughts (num_alternatives > 1), contrasted against
     Plan-and-Solve's single deterministic pass on the same choice.
  4. REFLEXION_NEEDED -- one part whose findings list a fabricated
     alternative ahead of the real one in the text (bait for a
     single-pass heuristic), so a single attempt is grounded-rejected
     and only a second trial, carrying Reflexion's own reflection
     forward, recovers -- also the scenario used for the
     grounded-vs-ungrounded LATS contrast, since the same fabricated
     candidate is exactly what an ungrounded evaluator has no way to
     catch.

All part/alternative data below is fake_db.py-shaped
({name: (id, name, qty)} / {part_id: [(alt_name,), ...]}), never touches
the real databases/ SQLite file, same convention as every existing
planning/tests/*.py file.
"""

from __future__ import annotations

from dataclasses import dataclass

from planning.fulfillment_decomposition import JobRequest


@dataclass
class Scenario:
    id: str
    title: str
    job: JobRequest
    parts: dict
    alternatives: dict
    notes: str


DECOMP_FIRST_FAVORED = Scenario(
    id="decomp_first_favored",
    title="Two required parts, both genuinely out of stock, both need an alternative",
    job=JobRequest(job_id="job-201", required_parts=["Brake Disc", "Timing Belt"]),
    parts={
        "Brake Disc": (10, "Brake Disc", 0),
        "Timing Belt": (11, "Timing Belt", 0),
        "Brake Disc XL": (12, "Brake Disc XL", 4),
        "Timing Belt Kit": (13, "Timing Belt Kit", 6),
    },
    alternatives={10: [("Brake Disc XL",)], 11: [("Timing Belt Kit",)]},
    notes=(
        "Every branch decomposition-first commits to up front turns out to be "
        "necessary here, so it pays for the same real tool calls dynamic "
        "decomposition would discover it needs anyway -- but with 1 LLM call "
        "(final synthesis) instead of dynamic's per-step decision loop "
        "(~1 decision call per check/altsearch node)."
    ),
)

DYNAMIC_FAVORED = Scenario(
    id="dynamic_favored",
    title="One well-stocked part, one out-of-stock part needing an alternative",
    job=JobRequest(job_id="job-202", required_parts=["Spark Plug", "Air Filter"]),
    parts={
        "Spark Plug": (20, "Spark Plug", 25),
        "Air Filter": (21, "Air Filter", 0),
        "Air Filter Premium": (22, "Air Filter Premium", 8),
    },
    alternatives={21: [("Air Filter Premium",)], 20: []},
    notes=(
        "Same shape as fulfillment_demo.py's own divergence case, new parts: "
        "dynamic decomposition observes Spark Plug's real stock is positive "
        "and never opens an alt-search branch for it; decomposition-first "
        "always opens (and pays tool calls for) both branches regardless."
    ),
)

LOOKAHEAD_NEEDED = Scenario(
    id="lookahead_needed",
    title="One out-of-stock part with two stocked alternatives to compare",
    job=JobRequest(job_id="job-203", required_parts=["Radiator Hose"]),
    parts={
        "Radiator Hose": (30, "Radiator Hose", 0),
        "Radiator Hose Std": (31, "Radiator Hose Std", 3),
        "Radiator Hose Heavy Duty": (32, "Radiator Hose Heavy Duty", 9),
    },
    alternatives={30: [("Radiator Hose Std",), ("Radiator Hose Heavy Duty",)]},
    notes=(
        "routing.classify_subtask(num_alternatives=2) actually returns "
        "COMPARE_ALTERNATIVES here (2 > 1) -- Tree of Thoughts explicitly "
        "ranks both candidates by declared quantity before picking; a single "
        "Plan-and-Solve pass has no comparison step and is shown picking "
        "whichever alternative its prompt happened to mention first."
    ),
)

REFLEXION_NEEDED = Scenario(
    id="reflexion_needed",
    title="One out-of-stock part; a fabricated alternative is listed ahead of the real one",
    job=JobRequest(job_id="job-204", required_parts=["Fuel Pump"]),
    parts={
        "Fuel Pump": (40, "Fuel Pump", 0),
        "Fuel Pump OEM": (41, "Fuel Pump OEM", 7),
        # "Fuel Pump Racing Edition" is deliberately NOT a key here -- it
        # does not exist in SpareParts, and is not a registered alternative
        # for Fuel Pump either (see `alternatives` below). Only the
        # findings text below claims it exists.
    },
    alternatives={40: [("Fuel Pump OEM",)]},
    notes=(
        "The findings text lists the fabricated 'Fuel Pump Racing Edition' "
        "before the real, in-stock, registered 'Fuel Pump OEM' -- a single "
        "attempt's first-mention heuristic reaches for the fabricated name "
        "and the grounded environment rejects it (it isn't in SpareParts at "
        "all); only Reflexion's cross-trial memory recovers on trial 2. The "
        "same fabricated candidate is also the failure case the ungrounded "
        "vendored Environment has no way to catch (see LATS ungrounded-vs-"
        "grounded row)."
    ),
)

FINDINGS_FOR_REFLEXION_NEEDED = (
    "Fuel Pump: id=40 quantity=0\n"
    "Fuel Pump: alternatives=[Fuel Pump Racing Edition (qty=50), Fuel Pump OEM (qty=7)]"
)

ALL_SCENARIOS: list[Scenario] = [
    DECOMP_FIRST_FAVORED,
    DYNAMIC_FAVORED,
    LOOKAHEAD_NEEDED,
    REFLEXION_NEEDED,
]

__all__ = [
    "ALL_SCENARIOS",
    "DECOMP_FIRST_FAVORED",
    "DYNAMIC_FAVORED",
    "FINDINGS_FOR_REFLEXION_NEEDED",
    "LOOKAHEAD_NEEDED",
    "REFLEXION_NEEDED",
    "Scenario",
]
