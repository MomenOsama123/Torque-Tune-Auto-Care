"""
context_eval/run_eval.py

Runs all four context-window management strategies (strategies.py) against
the same fixed long-context test suite (transcripts.py). For each
transcript: prune with the strategy, hand the pruned context plus the
final question to the same llm_client seam used by rag/ (mcp-server/rag/
llm_client.py), and check whether the critical detail survived pruning
well enough for the final answer to still contain it.

Reports, per strategy:
  - recalled: fraction of transcripts where the critical detail survived
    into the final answer
  - avg input tokens (final-answer call + any pruning-time LLM calls)
  - avg output tokens (same)
  - avg latency (pruning time + final-answer call time)

Run:
    python context_eval/run_eval.py
"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER = REPO_ROOT / "mcp-server"
RAG_DIR = MCP_SERVER / "rag"
CONTEXT_EVAL_DIR = Path(__file__).resolve().parent
for p in (str(MCP_SERVER), str(RAG_DIR), str(CONTEXT_EVAL_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from transcripts import TRANSCRIPTS  # noqa: E402
from strategies import (  # noqa: E402
    sliding_window,
    observation_masking,
    recursive_summarization,
    zone_based_pruning,
)
from llm_client import llm_call  # noqa: E402

STRATEGIES = {
    "sliding_window": sliding_window,
    "obs_masking": observation_masking,
    "recursive_summary": recursive_summarization,
    "zone_pruning": zone_based_pruning,
}


def render_context(messages) -> str:
    return "\n\n---\n\n".join(f"[{m['role']}] {m['content']}" for m in messages)


def is_correct(answer: str, expected_keywords: list[str]) -> bool:
    lowered = answer.lower()
    return any(kw.lower() in lowered for kw in expected_keywords)


def run_strategy(name: str, fn) -> dict:
    rows = []
    for case in TRANSCRIPTS:
        start = time.perf_counter()
        pruned, prune_in, prune_out, _ = fn(case["messages"])
        prune_elapsed = time.perf_counter() - start

        context = render_context(pruned)
        system = (
            "Answer the question using only the conversation context below. "
            "If the context doesn't say, say you don't have that information."
        )
        user = f"Context:\n{context}\n\nQuestion:\n{case['final_question']}"

        ans_start = time.perf_counter()
        answer, ans_in, ans_out = llm_call(system, user)
        ans_elapsed = time.perf_counter() - ans_start

        correct = is_correct(answer, case["expected_keywords"])
        rows.append({
            "id": case["id"],
            "correct": correct,
            "input_tokens": prune_in + ans_in,
            "output_tokens": prune_out + ans_out,
            "latency": prune_elapsed + ans_elapsed,
            "context_chars": len(context),
        })

    n = len(rows)
    return {
        "name": name,
        "rows": rows,
        "accuracy": sum(r["correct"] for r in rows) / n,
        "avg_input_tokens": sum(r["input_tokens"] for r in rows) / n,
        "avg_output_tokens": sum(r["output_tokens"] for r in rows) / n,
        "avg_latency": sum(r["latency"] for r in rows) / n,
        "avg_context_chars": sum(r["context_chars"] for r in rows) / n,
    }


def print_breakdown(summary: dict) -> None:
    print(f"\n{summary['name']} -- per-transcript results:")
    for r in summary["rows"]:
        mark = "PASS" if r["correct"] else "FAIL"
        print(f"  {mark}  {r['id']:>4}  in={r['input_tokens']:>5} out={r['output_tokens']:>4} "
              f"latency={r['latency']:.4f}s  ctx_chars={r['context_chars']}")


def print_table(summaries: list[dict]) -> None:
    n = len(TRANSCRIPTS)
    print(f"\n=== Context strategy comparison ({n} long-context test transcripts) ===")
    header = (f"{'Strategy':<18} | {'Recalled':<9} | {'Avg in-tok':<10} | "
              f"{'Avg out-tok':<11} | {'Avg latency':<11}")
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f"{s['name']:<18} | {s['accuracy']*n:.0f}/{n:<7}| "
            f"{s['avg_input_tokens']:<10.0f} | {s['avg_output_tokens']:<11.0f} | "
            f"{s['avg_latency']:<11.4f}"
        )


if __name__ == "__main__":
    summaries = [run_strategy(name, fn) for name, fn in STRATEGIES.items()]
    for s in summaries:
        print_breakdown(s)
    print_table(summaries)
