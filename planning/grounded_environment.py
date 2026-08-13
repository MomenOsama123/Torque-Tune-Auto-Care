"""
planning/grounded_environment.py

Issue 4: replaces the vendored toolkit's randomized, un-grounded
Environment (planning/vendor/planning_lab/algorithms/environment.py --
`round(self.rng.betavariate(5.0, 2.0), 4)`, ignores `state` entirely) with
a real evaluator for the Torque Tune spare-parts fulfillment problem, for
the one place SEAMS.md item 2 flagged as still open: the `Environment`
LATS uses to score/accept a candidate proceed/delay decision.

`GroundedFulfillmentEnvironment.evaluate(state) -> EnvironmentFeedback`
is a drop-in, duck-typed replacement for the vendored `Environment` --
`planning/vendor/planning_lab/algorithms/lats.py` only ever calls
`environment.evaluate(child.state)` and reads `.success`/`.score`/
`.details` off the (vendored, unmodified) `EnvironmentFeedback` model, so
nothing inside `algorithms/lats.py` (or plan_and_solve.py / tree_of_
thoughts.py) needs to change for this to work. Nothing in
planning/vendor/ is edited by this file.

Grounding source: the SAME real MCP tool implementations Issue 2 already
uses (mcp-server/tools/read_tools.py -- search_spare_part, check_stock,
suggest_alternative), against the SAME real database seam
(databases/db.get_connection). No new tool, table, column, or
supplier-availability concept is invented here -- per the module
docstring in planning/fulfillment_decomposition.py, this system has no
supplier-stock/lead-time tool, and this file does not add one.

What "grounded" means here, concretely -- the LATS candidate `state` is
free text (an LLM's proceed-with-part / proceed-with-alternative / delay
recommendation). This evaluator does not trust any number or name written
in that text. It parses out WHICH decision was made, then independently
re-queries the real database for the facts that decision depends on:

  - proceed-with-part <X>        -> does <X> exist in SpareParts? what is
                                     its REAL quantity right now (not
                                     whatever the candidate text claims)?
  - proceed-with-alternative <Y> -> does <Y> exist in SpareParts? what is
                                     its REAL quantity? is <Y> actually a
                                     registered AlternativeParts row for
                                     one of this job's required parts (not
                                     just some other real part the model
                                     happened to name)?
  - delay                        -> always grounded-safe: it claims no
                                     stock, so there is nothing to
                                     fabricate.

A candidate that names a real, in-stock, registered alternative is
accepted. A candidate that names a nonexistent part, an out-of-stock
part, or a real part that was never actually offered as an alternative
for this job is rejected -- regardless of what score a random evaluator
might have assigned it. See planning/tests/test_grounded_environment.py
for a deterministic demonstration of exactly that catch.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
for _p in (str(ROOT), str(MCP_SERVER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.read_tools import check_stock, search_spare_part, suggest_alternative  # noqa: E402

from planning.vendor.planning_lab.models import EnvironmentFeedback  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from planning.fulfillment_decomposition import JobRequest


# ---------------------------------------------------------------------
# Decision parsing -- reads WHICH decision the candidate text made. The
# real database is what confirms or rejects it, never the parsed text
# itself.
# ---------------------------------------------------------------------

_NAME = r"['\"]?([A-Za-z][A-Za-z0-9 \-]*?)['\"]?\s*(?:\(|[.,;]|$)"
_ALTERNATIVE_PATTERN = re.compile(rf"proceed with (?:the )?alternative\s*[:]?\s*{_NAME}", re.IGNORECASE)
_DELAY_PATTERN = re.compile(r"\bdelay\b", re.IGNORECASE)
_DIRECT_BARE_PATTERN = re.compile(
    r"proceed with (?:the )?(?:originally requested part|original part|the requested part)\b",
    re.IGNORECASE,
)
_DIRECT_NAMED_PATTERN = re.compile(rf"proceed with (?:the )?{_NAME}", re.IGNORECASE)


@dataclass
class _Decision:
    kind: str  # "alternative" | "direct" | "delay" | "unknown"
    part_name: str | None = None


def _extract_decision(state: str, job: "JobRequest") -> _Decision:
    text = state.strip()

    match = _ALTERNATIVE_PATTERN.search(text)
    if match:
        return _Decision(kind="alternative", part_name=match.group(1).strip())

    if _DELAY_PATTERN.search(text):
        return _Decision(kind="delay")

    if _DIRECT_BARE_PATTERN.search(text):
        if len(job.required_parts) == 1:
            return _Decision(kind="direct", part_name=job.required_parts[0])
        for part in job.required_parts:
            if part.lower() in text.lower():
                return _Decision(kind="direct", part_name=part)
        return _Decision(kind="unknown")

    match = _DIRECT_NAMED_PATTERN.search(text)
    if match:
        name = match.group(1).strip()
        if name.lower() not in {"alternative", "originally", "original"}:
            return _Decision(kind="direct", part_name=name)

    return _Decision(kind="unknown")


# ---------------------------------------------------------------------
# The grounded environment
# ---------------------------------------------------------------------


@dataclass
class GroundedFulfillmentEnvironment:
    """Real-database evaluator for the Torque Tune fulfillment LATS step.

    Constructed with the JobRequest being decided on, so a claimed
    alternative can be checked against THIS job's required parts (via the
    real AlternativeParts linkage), not just "some part exists somewhere".

    `tool_calls` counts real MCP tool invocations made while grounding a
    candidate -- transparency only, mirroring the tool-call accounting
    convention already used by `fulfillment_decomposition.Telemetry`; not
    a new invented capability.
    """

    job: "JobRequest"
    tool_calls: int = field(default=0)
    tool_call_log: list[str] = field(default_factory=list)

    def evaluate(self, state: str) -> EnvironmentFeedback:
        decision = _extract_decision(state, self.job)

        if decision.kind == "unknown":
            return EnvironmentFeedback(
                success=False,
                score=0.0,
                details=[
                    "Grounded environment could not identify a proceed-with-part, "
                    "proceed-with-alternative, or delay decision in this candidate; "
                    "an unverifiable decision is treated as ungrounded and rejected."
                ],
            )

        if decision.kind == "delay":
            return EnvironmentFeedback(
                success=True,
                score=0.7,
                details=["Delay claims no available stock, so there is nothing to ground-check."],
            )

        if decision.kind == "direct":
            return self._evaluate_direct(decision.part_name)  # type: ignore[arg-type]

        return self._evaluate_alternative(decision.part_name)  # type: ignore[arg-type]

    # -- individual groundable facts, per Issue 4 requirement 3 --------

    def part_exists(self, part_name: str) -> dict | None:
        """Real fact: does `part_name` exist in SpareParts? Returns
        {"id":..., "part_name":...} or None -- a real search_spare_part
        call, not an assumption."""
        self.tool_calls += 1
        self.tool_call_log.append(f"search_spare_part({part_name!r})")
        try:
            rows = search_spare_part(part_name)
        except ValueError:
            return None
        return {"id": rows[0][0], "part_name": rows[0][1]}

    def real_stock(self, part_id: int) -> int:
        """Real fact: current quantity for `part_id`, via a real
        check_stock call."""
        self.tool_calls += 1
        self.tool_call_log.append(f"check_stock({part_id})")
        return check_stock(part_id)["quantity"]

    def is_registered_alternative(self, alternative_name: str) -> bool:
        """Real fact: is `alternative_name` an actual AlternativeParts row
        for one of this job's required parts? Checked via real
        suggest_alternative calls -- never assumed from the candidate's
        own text."""
        for part in self.job.required_parts:
            found = self.part_exists(part)
            if found is None:
                continue
            self.tool_calls += 1
            self.tool_call_log.append(f"suggest_alternative({found['id']})")
            try:
                rows = suggest_alternative(found["id"])
            except ValueError:
                continue
            if any(row[0].lower() == alternative_name.lower() for row in rows):
                return True
        return False

    # -- grounded evaluation branches -----------------------------------

    def _evaluate_direct(self, part_name: str) -> EnvironmentFeedback:
        found = self.part_exists(part_name)
        if found is None:
            return EnvironmentFeedback(
                success=False,
                score=0.0,
                details=[f"{part_name!r} does not exist in the real SpareParts table."],
            )
        qty = self.real_stock(found["id"])
        if qty <= 0:
            return EnvironmentFeedback(
                success=False,
                score=0.0,
                details=[f"{part_name!r} (id={found['id']}) has real stock quantity={qty}; cannot proceed."],
            )
        return EnvironmentFeedback(
            success=True,
            score=1.0,
            details=[f"Verified: {part_name!r} (id={found['id']}) has real stock quantity={qty}."],
        )

    def _evaluate_alternative(self, alternative_name: str) -> EnvironmentFeedback:
        found = self.part_exists(alternative_name)
        if found is None:
            return EnvironmentFeedback(
                success=False,
                score=0.0,
                details=[f"Proposed alternative {alternative_name!r} does not exist in the real SpareParts table."],
            )
        qty = self.real_stock(found["id"])
        if qty <= 0:
            return EnvironmentFeedback(
                success=False,
                score=0.0,
                details=[
                    f"Proposed alternative {alternative_name!r} (id={found['id']}) has real stock "
                    f"quantity={qty}; not actually available."
                ],
            )
        if not self.is_registered_alternative(alternative_name):
            return EnvironmentFeedback(
                success=False,
                score=0.0,
                details=[
                    f"{alternative_name!r} exists and is in stock, but is not a registered "
                    f"AlternativeParts entry for any required part in job {self.job.job_id!r}; "
                    "rejecting an unrelated real part is not the same as accepting a valid substitute."
                ],
            )
        return EnvironmentFeedback(
            success=True,
            score=1.0,
            details=[
                f"Verified: alternative {alternative_name!r} (id={found['id']}) has real stock "
                f"quantity={qty} and is a registered alternative for job {self.job.job_id!r}."
            ],
        )


__all__ = ["GroundedFulfillmentEnvironment"]
