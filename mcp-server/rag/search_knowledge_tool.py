"""
mcp-server/rag/search_knowledge_tool.py

Wires the RAG layer into the live MCP server as a real tool, the same way
the original search_policy tool did -- but now backed by hybrid search
(vector + keyword, see retrieval_eval/ for why hybrid was chosen over
naive/agentic as the default) over all four knowledge documents, and
Self-RAG-style verification before anything is returned to the caller.

Registered in server.py via:
    from rag import search_knowledge_tool  # noqa: F401
"""

from app import mcp
from hybrid_rag import build_hybrid_rag
from self_rag_check import verify

# Built once at import time -- embedding/index construction is a one-time
# cost, not something to redo on every tool call.
_rag = build_hybrid_rag()


@mcp.tool()
def search_company_knowledge(question: str) -> dict:
    """
    Answer a question using the company's knowledge base: warranty terms,
    technical service bulletins, diagnostic/repair procedures, and general
    company policy. Use this for questions the inventory/order tools can't
    answer directly -- e.g. "is this part still under warranty", "is this
    a known TSB issue", "what's the right repair sequence for X".

    Every answer is grounded and verified: if the retrieved knowledge
    isn't actually relevant, or the answer isn't actually supported by it,
    this returns grounded=False with an explicit refusal instead of a
    guess.
    """
    result = _rag.answer(question)
    verified = verify(question, result.answer, result.retrieved)

    return {
        "answer": verified.answer,
        "grounded": verified.grounded,
        "sources": [
            {"document": c.source, "section": c.section}
            for c in verified.kept_chunks
        ],
        "dropped_as_irrelevant": [
            {"document": c.source, "section": c.section}
            for c in verified.dropped_chunks
        ],
    }


if __name__ == "__main__":
    r = search_company_knowledge("What does TSB-2024-118 say?")
    import json
    print(json.dumps(r, indent=2))
