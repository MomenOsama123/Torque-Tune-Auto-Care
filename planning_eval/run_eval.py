"""
planning_eval/run_eval.py

Issue 7. Runs every required comparison against the fixed scenarios in
planning_eval/scenarios.py, writes the full comparison table to
planning_eval/results/comparison_table.md, and one JSON trace per run to
planning_eval/results/artifacts/ -- extending the vendored toolkit's own
save_artifact() payload shape (planning/vendor/planning_lab/cli.py:
mode/model/goal/...->result), not a second logging system.

Run:
    python planning_eval/run_eval.py

Works with or without ANTHROPIC_API_KEY set (planning/model_provider.py's
own real-or-offline seam decides which); the offline path is fully
deterministic (see model_provider.py's docstrings for exactly which
heuristic answers which prompt), so the SAME comparison table is
reproducible without a network call, and a second run with a live key
re-measures the same scenarios against real Claude output.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_ROOT = ROOT / "mcp-server"
for _p in (str(ROOT), str(MCP_SERVER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from planning.model_provider import MODEL  # noqa: E402
from planning_eval.harness import (  # noqa: E402
    run_decomposition_case,
    run_lats_grounding_case,
    run_lookahead_case,
    run_reflexion_case,
    run_self_refine_case,
)
from planning_eval.scenarios import (  # noqa: E402
    DECOMP_FIRST_FAVORED,
    DYNAMIC_FAVORED,
    FINDINGS_FOR_REFLEXION_NEEDED,
    LOOKAHEAD_NEEDED,
    REFLEXION_NEEDED,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ARTIFACTS_DIR = RESULTS_DIR / "artifacts"


def save_artifact(row, run_index: int) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "mode": row.method,
        "model": MODEL,
        "concern": row.concern,
        "case": row.case,
        "success": row.success,
        "llm_calls": row.llm_calls,
        "tool_calls": row.tool_calls,
        "total_tokens": row.total_tokens,
        "token_source": row.token_source,
        "latency_seconds": row.latency_seconds,
        "result": row.output,
        **row.trace,
    }
    path = ARTIFACTS_DIR / f"run-{stamp}-{run_index:03d}-{row.case}-{row.method}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def render_table(rows) -> str:
    header = (
        "| Concern | Case | Method | Success | LLM calls | Tool calls | "
        "Total tokens (source) | Latency (s) | Detail |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = [header]
    for row in rows:
        detail = row.detail.replace("\n", " ")[:120]
        lines.append(
            f"| {row.concern} | {row.case} | {row.method} | {'success' if row.success else 'fail'} | "
            f"{row.llm_calls} | {row.tool_calls} | {row.total_tokens} ({row.token_source}) | "
            f"{row.latency_seconds:.4f} | {detail} |\n"
        )
    return "".join(lines)


def main() -> None:
    rows = []
    rows += run_decomposition_case(DECOMP_FIRST_FAVORED)
    rows += run_decomposition_case(DYNAMIC_FAVORED)
    rows += run_lookahead_case(LOOKAHEAD_NEEDED)
    rows += run_lats_grounding_case(REFLEXION_NEEDED, FINDINGS_FOR_REFLEXION_NEEDED)
    rows += run_reflexion_case(REFLEXION_NEEDED, FINDINGS_FOR_REFLEXION_NEEDED)

    # Self-Refine needs a real decision text to draft a notification about
    # -- reuse Reflexion's own recovered decision from this same run rather
    # than inventing a separate one.
    reflexion_row = next(r for r in rows if r.method.startswith("reflexion"))
    rows.append(run_self_refine_case(REFLEXION_NEEDED, reflexion_row.output))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(rows):
        save_artifact(row, i)

    table = render_table(rows)
    (RESULTS_DIR / "comparison_table.md").write_text(table, encoding="utf-8")
    print(table)
    print(f"\n{len(rows)} runs. Table: {RESULTS_DIR / 'comparison_table.md'}")
    print(f"Artifacts: {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
