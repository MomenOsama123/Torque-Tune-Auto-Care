"""
mcp-server/rag/self_rag_check.py

Self-RAG-style verification (see the "Self RAG" / "Reflection Tokens"
slides): don't trust whatever the retriever or the generator handed back --
ask explicitly:

  1. Post-retrieval: is each retrieved chunk actually relevant to the query?
  2. Post-generation: is the generated answer actually supported by the
     (relevant) retrieved context, or did the model add something not in it?

This runs after any of naive_rag / hybrid_rag / agentic_rag and has a
visible consequence when it fails: irrelevant chunks are dropped before
the context reaches the answer check, and an unsupported answer is
replaced with an explicit "not grounded" notice instead of being shown
to the user as if it were reliable.
"""

import json
import re
from dataclasses import dataclass

from chunking import Chunk
from llm_client import llm_call

RELEVANCE_PROMPT = """Is the passage below relevant to answering the question?
Respond with ONLY a JSON object: {{"relevant": true|false, "reasoning": "..."}}

Question: {question}

Passage:
{passage}
"""

SUPPORT_PROMPT = """Is the answer below fully supported by the context, with no
claims added that aren't in the context? Respond with ONLY a JSON object:
{{"supported": true|false, "reasoning": "..."}}

Context:
{context}

Answer:
{answer}
"""


@dataclass
class VerifiedResult:
    answer: str
    grounded: bool
    kept_chunks: list[Chunk]
    dropped_chunks: list[Chunk]
    relevance_notes: list[str]
    support_note: str


def check_relevance(question: str, chunk: Chunk) -> tuple[bool, str]:
    raw, _, _ = llm_call(
        system="You are a strict relevance grader.",
        user=RELEVANCE_PROMPT.format(question=question, passage=chunk.text),
        want_json=True,
    )
    parsed = _safe_json(raw, fallback={"relevant": _heuristic_relevance(question, chunk), "reasoning": "mock heuristic (token overlap)"})
    return bool(parsed.get("relevant", False)), parsed.get("reasoning", "")


def check_support(question: str, answer: str, context: str) -> tuple[bool, str]:
    raw, _, _ = llm_call(
        system="You are a strict groundedness grader.",
        user=SUPPORT_PROMPT.format(context=context, answer=answer),
        want_json=True,
    )
    parsed = _safe_json(
        raw,
        fallback={"supported": _heuristic_support(answer, context), "reasoning": "mock heuristic (n-gram overlap)"},
    )
    return bool(parsed.get("supported", False)), parsed.get("reasoning", "")


def verify(question: str, answer: str, retrieved: list[Chunk]) -> VerifiedResult:
    kept, dropped, notes = [], [], []
    for chunk in retrieved:
        is_relevant, reason = check_relevance(question, chunk)
        notes.append(f"[{chunk.section}] relevant={is_relevant} -- {reason}")
        (kept if is_relevant else dropped).append(chunk)

    context = "\n\n---\n\n".join(c.text for c in kept) if kept else ""
    is_supported, support_reason = check_support(question, answer, context) if kept else (False, "no relevant chunks survived the relevance check")

    final_answer = answer if (kept and is_supported) else (
        "I can't answer this from verified sources -- the retrieved context "
        "either wasn't relevant or doesn't support a grounded answer."
    )

    return VerifiedResult(
        answer=final_answer,
        grounded=bool(kept and is_supported),
        kept_chunks=kept,
        dropped_chunks=dropped,
        relevance_notes=notes,
        support_note=support_reason,
    )


# ---- mock-mode heuristics (used only when llm_client has no API key) ----
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "does", "do", "did", "say", "says", "said", "to", "of", "in", "on",
    "for", "and", "or", "but", "with", "about", "it", "its", "as", "at",
}


def _tokens(text: str) -> set[str]:
    raw = set(re.findall(r"[a-z0-9-]+", text.lower()))
    return raw - _STOPWORDS


def _heuristic_relevance(question: str, chunk: Chunk) -> bool:
    overlap = _tokens(question) & _tokens(chunk.text)
    return len(overlap) >= 1


def _heuristic_support(answer: str, context: str) -> bool:
    if not answer.strip():
        return False
    a_tokens = _tokens(answer)
    c_tokens = _tokens(context)
    if not a_tokens:
        return False
    return len(a_tokens & c_tokens) / len(a_tokens) >= 0.5


def _safe_json(raw: str, fallback: dict) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


if __name__ == "__main__":
    from hybrid_rag import build_hybrid_rag

    rag = build_hybrid_rag()

    print("--- Case 1: should pass verification ---")
    q1 = "What does TSB-2024-118 say?"
    r1 = rag.answer(q1)
    v1 = verify(q1, r1.answer, r1.retrieved)
    print(f"grounded={v1.grounded}")
    print(f"kept={[c.section for c in v1.kept_chunks]}")
    print(f"dropped={[c.section for c in v1.dropped_chunks]}")
    print(f"final answer: {v1.answer[:120]}...\n")

    print("--- Case 2: forced failure (unsupported claim injected) ---")
    fabricated_answer = (
        "TSB-2024-118 requires replacing the entire engine block and voids "
        "all warranties immediately, per company policy section 9."
    )
    v2 = verify(q1, fabricated_answer, r1.retrieved)
    print(f"grounded={v2.grounded}")
    print(f"support_note={v2.support_note}")
    print(f"final answer shown to user: {v2.answer}")
