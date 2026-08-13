"""
retrieval_eval/run_eval.py

Runs naive RAG, hybrid RAG, and agentic RAG against the same fixed test
set (test_questions.py), each answer passed through the Self-RAG-style
verification (self_rag_check.py) before scoring -- so the comparison
table reflects what the user would actually see, not raw retrieval.

For each architecture, reports:
  - accuracy: fraction of questions where every expected keyword appears
    (case-insensitive) in the verified final answer
  - avg input tokens / query
  - avg output tokens / query
  - avg latency / query

Run:
    python retrieval_eval/run_eval.py
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = REPO_ROOT / "mcp-server"
RAG_DIR = MCP_SERVER / "rag"
for p in (str(MCP_SERVER), str(RAG_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_questions import TEST_QUESTIONS  # noqa: E402

from agentic_rag import build_agentic_rag  # noqa: E402
from hybrid_rag import build_hybrid_rag  # noqa: E402
from naive_rag import build_naive_rag  # noqa: E402
from self_rag_check import verify  # noqa: E402


def is_correct(answer: str, expected_keywords: list[str]) -> bool:
    lowered = answer.lower()
    return all(kw.lower() in lowered for kw in expected_keywords)


def top1_hit(retrieved, expected_keywords: list[str]) -> bool:
    """Stricter secondary signal: is the SINGLE highest-ranked retrieved
    chunk actually the on-topic one? On a small corpus, top_k=3 often
    contains the right chunk regardless of ranking quality (see naive vs
    hybrid on H1 in the README) -- this metric is what actually separates
    architectures instead of getting drowned out by that effect."""
    if not retrieved:
        return False
    top_text = retrieved[0].text.lower()
    return any(kw.lower() in top_text for kw in expected_keywords)


def run_architecture(name: str, rag_obj) -> dict:
    rows = []
    for q in TEST_QUESTIONS:
        start = time.perf_counter()
        result = rag_obj.answer(q["question"])
        verified = verify(q["question"], result.answer, result.retrieved)
        latency = time.perf_counter() - start  # includes verification calls too

        correct = is_correct(verified.answer, q["expected_keywords"])
        top1 = top1_hit(result.retrieved, q["expected_keywords"])
        rows.append({
            "id": q["id"],
            "category": q["category"],
            "correct": correct,
            "top1": top1,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency": latency,
        })

    n = len(rows)
    accuracy = sum(r["correct"] for r in rows) / n
    top1_accuracy = sum(r["top1"] for r in rows) / n
    avg_in = sum(r["input_tokens"] for r in rows) / n
    avg_out = sum(r["output_tokens"] for r in rows) / n
    avg_latency = sum(r["latency"] for r in rows) / n

    return {
        "name": name,
        "rows": rows,
        "accuracy": accuracy,
        "top1_accuracy": top1_accuracy,
        "avg_input_tokens": avg_in,
        "avg_output_tokens": avg_out,
        "avg_latency": avg_latency,
    }


def print_per_question_breakdown(summary: dict) -> None:
    print(f"\n{summary['name']} -- per-question results:")
    for r in summary["rows"]:
        mark = "✓" if r["correct"] else "✗"
        top1_mark = "✓" if r["top1"] else "✗"
        print(f"  answer={mark} top1={top1_mark}  {r['id']:>3} [{r['category']:<7}] "
              f"in={r['input_tokens']:>5} out={r['output_tokens']:>4} "
              f"latency={r['latency']:.3f}s")


def print_comparison_table(summaries: list[dict]) -> None:
    n = len(TEST_QUESTIONS)
    print(f"\n=== Comparison table ({n} test questions) ===")
    header = (f"{'Architecture':<12} | {'Answer acc':<11} | {'Top-1 acc':<10} | "
              f"{'Avg in-tok':<10} | {'Avg out-tok':<11} | {'Avg latency':<11}")
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f"{s['name']:<12} | "
            f"{s['accuracy']*n:.0f}/{n:<8}| "
            f"{s['top1_accuracy']*n:.0f}/{n:<7}| "
            f"{s['avg_input_tokens']:<10.0f} | "
            f"{s['avg_output_tokens']:<11.0f} | "
            f"{s['avg_latency']:<11.3f}"
        )


if __name__ == "__main__":
    print("Building RAG systems (shared vector store per architecture)...")
    naive = build_naive_rag()
    hybrid = build_hybrid_rag()
    agentic = build_agentic_rag()

    summaries = [
        run_architecture("naive", naive),
        run_architecture("hybrid", hybrid),
        run_architecture("agentic", agentic),
    ]

    for s in summaries:
        print_per_question_breakdown(s)

    print_comparison_table(summaries)
