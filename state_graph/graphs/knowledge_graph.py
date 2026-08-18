"""
state_graph/graphs/knowledge_graph.py

State Problem 3: answering a technician's question from the company
knowledge base, where a single retrieval pass sometimes isn't enough --
retrieval_eval/ already measured cases where a one-shot top-k=3 hybrid
search finds the right procedure but misses the specific warranty
section it cross-references. That's a real, multi-turn decision (retry
with a different strategy, or admit the KB doesn't cover it), not a
single tool call -- and if nobody answers it, a technician is left
without an answer mid-repair, which is exactly the kind of thing that
should be checkpointed and escalated rather than silently dropped.

Intelligent techniques embedded in the nodes:
  - RAG Architecture: `hybrid_search` calls the real, already-built
    hybrid (vector + BM25) RAG + Self-RAG verification tool
    (mcp-server/rag/search_knowledge_tool.py) as the fast, default path
    -- the same one retrieval_eval/ shows wins on Torque Tune's actual
    query mix.
  - Constrained ReAct: `agentic_retry` only fires when the first pass
    isn't grounded, and calls the real, already-built agentic RAG loop
    (mcp-server/rag/agentic_rag.py) -- Question -> Reason -> Retrieve ->
    Observe -> Reason again -> Retrieve again, constrained to retrieval
    actions only, capped at MAX_HOPS in that module. This is a second,
    different technique from the same required list, escalated to only
    when the cheaper one fails -- not run unconditionally.

Graph shape:

    hybrid_search -*-> deliver_answer -> END
                    \\-> agentic_retry -*-> deliver_answer -> END
                                        \\-> needs_human_review -> END
"""

from __future__ import annotations

from typing import Any

from state_graph.bootstrap import memory_manager, server
from state_graph.engine import END, StateGraph

GRAPH_NAME = "knowledge_qa"


def hybrid_search(state: dict) -> dict[str, Any]:
    result = server.mcp._tools["search_company_knowledge"](state["question"])
    return {
        "answer": result["answer"],
        "grounded": result["grounded"],
        "sources": result["sources"],
        "attempts": 1,
    }


def _route_after_hybrid(state: dict) -> str:
    return "grounded" if state["grounded"] else "retry"


def agentic_retry(state: dict) -> dict[str, Any]:
    """Escalates to the agentic (multi-hop) RAG loop, then re-verifies
    with the same Self-RAG check the hybrid path used, so both paths are
    held to the same grounding bar."""
    # Imported lazily (not at module top) so importing this file never
    # pays the cost of building a second vector index unless a retry
    # actually happens.
    from agentic_rag import build_agentic_rag
    from self_rag_check import verify

    rag = build_agentic_rag()
    result = rag.answer(state["question"])
    verified = verify(state["question"], result.answer, result.retrieved)
    return {
        "answer": verified.answer,
        "grounded": verified.grounded,
        "sources": [{"document": c.source, "section": c.section} for c in verified.kept_chunks],
        "attempts": state["attempts"] + 1,
        "hops": result.hops,
    }


def _route_after_retry(state: dict) -> str:
    return "grounded" if state["grounded"] else "unresolved"


def deliver_answer(state: dict) -> dict[str, Any]:
    memory_manager.add_interaction(
        "tool_output",
        {
            "tool": "search_company_knowledge",
            "question": state["question"],
            "answer": state["answer"],
            "attempts": state["attempts"],
        },
    )
    return {"final_status": "answered"}


def needs_human_review(state: dict) -> dict[str, Any]:
    """A genuine knowledge-base gap is a normal business outcome, not a
    bug -- logged for a human to add the missing document, not filed as
    a Failure Ticket (see state_graph/tickets.py's module docstring on
    that distinction)."""
    memory_manager.add_interaction(
        "assistant",
        f"Could not answer from verified sources after {state['attempts']} attempts: "
        f"{state['question']!r}. Flagged for knowledge-base review.",
    )
    return {"final_status": "needs_kb_update"}


def build_graph() -> StateGraph:
    g = StateGraph(name=GRAPH_NAME)
    g.add_node("hybrid_search", hybrid_search)
    g.add_node("agentic_retry", agentic_retry)
    g.add_node("deliver_answer", deliver_answer)
    g.add_node("needs_human_review", needs_human_review)

    g.set_entry_point("hybrid_search")
    g.add_conditional_edges(
        "hybrid_search", _route_after_hybrid, {"grounded": "deliver_answer", "retry": "agentic_retry"}
    )
    g.add_conditional_edges(
        "agentic_retry",
        _route_after_retry,
        {"grounded": "deliver_answer", "unresolved": "needs_human_review"},
    )
    g.add_edge("deliver_answer", END)
    g.add_edge("needs_human_review", END)
    return g
