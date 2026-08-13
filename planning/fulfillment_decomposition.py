"""
planning/fulfillment_decomposition.py

Issue 2: decomposition-first and dynamic/interleaved decomposition for
Torque Tune's real recurring request:

    "Prepare spare parts for a repair job when one or more required
     parts are out of stock."

Both are adapted from planning/vendor/planning_lab (the forked reference
toolkit, unmodified -- see planning/vendor/ATTRIBUTION.md). Neither lets
the LLM write free prose for a node the way the toolkit's own demo
(decompose_goal / execute_plan in vendor/planning_lab/algorithms/
decomposition.py) does: every non-synthesis node is a real call into
mcp-server/tools/read_tools.py against the actual database. Confirmed by
inspection (Issue 2 step 1) before writing anything here:

    search_spare_part(part_name) -> rows; row[0]=id, row[1]=part_name
                                     (SELECT * FROM SpareParts, per
                                     databases/schema.sql column order)
    check_stock(part_id)         -> {"part_id":..., "quantity":...}
    suggest_alternative(part_id) -> [(alt_part_name,), ...] -- NAMES
                                     ONLY. The id/stock of each
                                     alternative is unknown until you
                                     search_spare_part() it again -- a
                                     real dependency chain, not an
                                     invented one.

There is no MCP tool for supplier stock/lead time (Suppliers only has
contact info -- confirmed against databases/schema.sql and by grepping
mcp-server/ for "supplier"; only a RAG knowledge-base doc exists, not a
callable tool). "No part and no alternative in stock" is therefore a
genuine dead end in this system: the synthesis node reports that outcome
for a human to act on, it does not fabricate a supplier-check step.

KNOWN CONSTRAINT (from planning_lab/models.py, inspected, not invented):
Plan.tasks is capped at 8 (Field(min_length=1, max_length=8)).
build_plan_first() uses 2 tasks per required part + 1 synthesis task, so
a single decomposition-first plan supports at most 3 required parts
(3*2+1=7). A job with more than 3 parts will raise a pydantic
ValidationError from the vendored Plan model -- surfaced, not silently
truncated. Splitting a >3-part job into multiple plans is future work,
not addressed in Issue 2.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
for _p in (str(ROOT), str(MCP_SERVER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.read_tools import search_spare_part, check_stock, suggest_alternative  # noqa: E402

from planning.vendor.planning_lab.models import Plan, Task  # noqa: E402
from planning.vendor.planning_lab.algorithms.dynamic_decomposition import DynamicDecision  # noqa: E402


@dataclass
class JobRequest:
    """One repair job's required-parts list. Each entry must match (or
    substring-match, per search_spare_part's LIKE query) a
    SpareParts.part_name."""

    job_id: str
    required_parts: list[str]


@dataclass
class Telemetry:
    """Real call accounting, not an estimate -- feeds the Issue 7
    comparison table, which must score every method on real calls."""

    tool_calls: int = 0
    llm_calls: int = 0
    tool_call_log: list[str] = field(default_factory=list)


def _slug(part_name: str) -> str:
    return part_name.lower().replace(" ", "_")


def _find_part(part_name: str, telemetry: Telemetry) -> dict | None:
    """search_spare_part + shape the first match. Returns None (not an
    exception) when nothing matches -- 'part unknown to inventory' is an
    expected branch here, not a failure of this function."""
    telemetry.tool_calls += 1
    telemetry.tool_call_log.append(f"search_spare_part({part_name!r})")
    try:
        rows = search_spare_part(part_name)
    except ValueError:
        return None
    row = rows[0]
    return {"id": row[0], "part_name": row[1]}


def _stock(part_id: int, telemetry: Telemetry) -> int:
    telemetry.tool_calls += 1
    telemetry.tool_call_log.append(f"check_stock({part_id})")
    return check_stock(part_id)["quantity"]


def _alternative_names(part_id: int, telemetry: Telemetry) -> list[str]:
    telemetry.tool_calls += 1
    telemetry.tool_call_log.append(f"suggest_alternative({part_id})")
    try:
        rows = suggest_alternative(part_id)
    except ValueError:
        return []
    return [row[0] for row in rows]


# ---------------------------------------------------------------------
# Decomposition-first
# ---------------------------------------------------------------------


def build_plan_first(job: JobRequest) -> Plan:
    """Commits to the full worst-case DAG up front: every required part
    gets an alternative-search branch unconditionally, before any real
    check_stock result is known. Uses the vendored Task/Plan models
    directly, so cycle rejection and topological batching are inherited
    from planning_lab/models.py, not reimplemented.

    Raises pydantic.ValidationError via Plan.__init__ if job has more
    than 3 required parts (see module docstring) or if a part name
    contains characters the Task.id slug can't encode."""
    tasks: list[Task] = []
    decide_deps: list[str] = []
    for part in job.required_parts:
        slug = _slug(part)
        check_id = f"check_{slug}"
        alt_id = f"altsearch_{slug}"
        tasks.append(Task(id=check_id, instruction=f"check_stock for {part!r}", depends_on=[]))
        tasks.append(Task(id=alt_id, instruction=f"suggest_alternative for {part!r}", depends_on=[check_id]))
        decide_deps.extend([check_id, alt_id])
    tasks.append(Task(id="decide", instruction="Synthesize a proceed/delay recommendation", depends_on=decide_deps))
    return Plan(goal=f"Fulfill parts for job {job.job_id}", tasks=tasks)


def execute_plan_first(plan: Plan, job: JobRequest, llm) -> tuple[dict[str, str], Telemetry]:
    """Executes plan.execution_batches() -- the vendored toolkit's own
    topological batching, reused unmodified -- but dispatches each node
    to a real tool call instead of free LLM prose. The toolkit's own
    execute_plan() always calls llm.invoke() per node; that's exactly
    the 'generic demo prompt' behaviour Issue 2 said not to keep."""
    telemetry = Telemetry()
    outputs: dict[str, str] = {}
    part_by_slug = {_slug(p): p for p in job.required_parts}

    for batch in plan.execution_batches():
        for task_id in batch:
            if task_id == "decide":
                continue  # handled after the loop, once every batch is in
            kind, slug = task_id.split("_", 1)
            part = part_by_slug[slug]
            if kind == "check":
                found = _find_part(part, telemetry)
                if found is None:
                    outputs[task_id] = f"{part}: not found in SpareParts"
                    continue
                qty = _stock(found["id"], telemetry)
                outputs[task_id] = f"{part}: id={found['id']} quantity={qty}"
            elif kind == "altsearch":
                check_output = outputs[f"check_{slug}"]
                if "not found" in check_output:
                    outputs[task_id] = f"{part}: skipped, part unknown to inventory"
                    continue
                part_id = int(check_output.split("id=")[1].split(" ")[0])
                names = _alternative_names(part_id, telemetry)
                details = []
                for alt_name in names:
                    alt = _find_part(alt_name, telemetry)
                    if alt is None:
                        continue
                    alt_qty = _stock(alt["id"], telemetry)
                    details.append(f"{alt_name} (qty={alt_qty})")
                outputs[task_id] = f"{part}: alternatives=[{', '.join(details) or 'none'}]"

    telemetry.llm_calls += 1
    summary = "\n".join(outputs[t.id] for t in plan.tasks if t.id != "decide")
    decision = llm.invoke([
        (
            "system",
            "You recommend proceed-with-part, proceed-with-alternative, or delay for a "
            "repair job, based only on the real findings given. Never invent a supplier "
            "check; none exists in this system.",
        ),
        ("human", f"Job {job.job_id} findings:\n{summary}\n\nRecommend one action and say why, in 2-3 sentences."),
    ])
    outputs["decide"] = decision.content.strip()
    return outputs, telemetry


# ---------------------------------------------------------------------
# Dynamic / interleaved decomposition
# ---------------------------------------------------------------------


def dynamic_fulfillment(job: JobRequest, llm, max_steps: int = 12) -> tuple[list[tuple[str, str]], Telemetry]:
    """Adapts the vendored dynamic_decomposition() loop shape (decide the
    next step from real observations so far -> execute it -> observe ->
    repeat -- see planning/vendor/planning_lab/algorithms/
    dynamic_decomposition.py) but the 'execute' half is a real tool call,
    and the decision is grounded in the real result of the previous call.
    This is what lets it skip the alternative-search branch entirely for
    a part with sufficient stock -- unlike build_plan_first() above,
    which always builds that branch regardless of outcome. See
    fulfillment_demo.py for a concrete run showing the divergence."""
    telemetry = Telemetry()
    history: list[tuple[str, str]] = []
    remaining = list(job.required_parts)
    pending_alt_search: str | None = None

    for _ in range(max_steps):
        if not remaining and pending_alt_search is None:
            break
        observation = "\n".join(f"{t}: {r}" for t, r in history) or "None"
        telemetry.llm_calls += 1
        decision = llm.with_structured_output(DynamicDecision, method="json_schema").invoke([
            (
                "system",
                "You are an adaptive fulfillment planner. Only decide to search for an "
                "alternative when the last check_stock observation actually showed "
                "insufficient quantity.",
            ),
            (
                "human",
                f"Job {job.job_id}, remaining required parts: {remaining}, "
                f"pending alternative search: {pending_alt_search}\n"
                f"Observations so far:\n{observation}\n"
                "Set next_task to 'check:<part>' or 'altsearch:<part>', "
                "or done=true once every part is resolved.",
            ),
        ])
        if decision.done:
            break
        action, _, target = decision.next_task.partition(":")
        if action == "check" and target in remaining:
            found = _find_part(target, telemetry)
            if found is None:
                result = f"{target}: not found in SpareParts"
            else:
                qty = _stock(found["id"], telemetry)
                result = f"{target}: id={found['id']} quantity={qty}"
                if qty <= 0:
                    pending_alt_search = target
            remaining.remove(target)
            history.append((f"check:{target}", result))
        elif action == "altsearch" and target == pending_alt_search:
            check_result = next(r for t, r in history if t == f"check:{target}")
            part_id = int(check_result.split("id=")[1].split(" ")[0])
            names = _alternative_names(part_id, telemetry)
            details = []
            for alt_name in names:
                alt = _find_part(alt_name, telemetry)
                if alt is None:
                    continue
                alt_qty = _stock(alt["id"], telemetry)
                details.append(f"{alt_name} (qty={alt_qty})")
            history.append((f"altsearch:{target}", f"alternatives=[{', '.join(details) or 'none'}]"))
            pending_alt_search = None
        else:
            # Ungrounded/invalid decision (e.g. hallucinated part name) --
            # stop rather than guess what the model meant.
            break

    telemetry.llm_calls += 1
    summary = "\n".join(f"{t}: {r}" for t, r in history)
    decision_msg = llm.invoke([
        (
            "system",
            "You recommend proceed-with-part, proceed-with-alternative, or delay for a "
            "repair job, based only on the real findings given. Never invent a supplier "
            "check; none exists in this system.",
        ),
        ("human", f"Job {job.job_id} findings:\n{summary}\n\nRecommend one action and say why, in 2-3 sentences."),
    ])
    history.append(("decide", decision_msg.content.strip()))
    return history, telemetry
