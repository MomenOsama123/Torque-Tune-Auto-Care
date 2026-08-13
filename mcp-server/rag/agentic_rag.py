"""
mcp-server/rag/agentic_rag.py

Agentic RAG (see the "Agentic RAG" slide): the agent decides what to
retrieve, when to retrieve, and whether additional retrieval is
necessary -- versus naive/hybrid RAG's fixed one-shot retrieve-then-
generate.

Loop: Question -> Reason -> Retrieve -> Observe -> Reason again ->
Retrieve again (if needed) -> Answer.

Why this earns its place in this corpus specifically: the multi-part
diagnostic questions in diagnostic_repair_procedures.md explicitly chain a
procedure step to a TSB and a warranty section ("cross-check against
technical_service_bulletins.md and supplier_warranty_terms.md"). A single
top-k=3 retrieval from hybrid_rag.py often returns the procedure but not
the specific warranty section it points to (see retrieval_eval for the
measured miss rate) -- agentic RAG's second hop is what closes that gap.
"""

import time
from dataclasses import dataclass

from chunking import Chunk, load_chunks
from embeddings import Embedder
from hybrid_rag import HybridRag
from keyword_search import KeywordIndex
from llm_client import llm_call
from vector_store import VectorStore, build_vector_store

MAX_HOPS = 3

DECISION_PROMPT = """You are deciding whether the retrieved context below is
enough to answer the question, or whether another retrieval round is needed.

Question:
{question}

Retrieved so far:
{context}

Respond with ONLY a JSON object:
{{"reasoning": "...", "retrieve_again": true|false, "next_query": "... or null"}}
"""


@dataclass
class AgenticRagResult:
    answer: str
    retrieved: list[Chunk]
    hops: int
    input_tokens: int
    output_tokens: int
    latency_seconds: float


class AgenticRag:
    def __init__(self, hybrid: HybridRag):
        self.hybrid = hybrid  # each hop's retrieval reuses hybrid search

    def answer(self, question: str, top_k_per_hop: int = 2) -> AgenticRagResult:
        start = time.perf_counter()
        total_in, total_out = 0, 0

        retrieved: list[Chunk] = []
        current_query = question

        for hop in range(1, MAX_HOPS + 1):
            ids = self.hybrid._merged_ranking(current_query, top_k_per_hop)
            new_chunks = [self.hybrid.chunks[i] for i in ids if self.hybrid.chunks[i] not in retrieved]
            retrieved.extend(new_chunks)

            context = "\n\n---\n\n".join(c.text for c in retrieved)
            decision_prompt = DECISION_PROMPT.format(question=question, context=context)
            raw, in_tok, out_tok = llm_call(
                system="You are a careful retrieval-planning assistant.",
                user=decision_prompt,
                want_json=True,
            )
            total_in += in_tok
            total_out += out_tok

            decision = _parse_decision(raw)
            if not decision["retrieve_again"] or hop == MAX_HOPS:
                break
            current_query = decision["next_query"] or question

        final_context = "\n\n---\n\n".join(c.text for c in retrieved)
        final_prompt = (
            f"Answer using only this context. If the context does not contain "
            f"the answer, say so explicitly -- never guess.\n\nContext:\n"
            f"{final_context}\n\nQuestion:\n{question}"
        )
        text, in_tok, out_tok = llm_call(system="You are a precise assistant.", user=final_prompt)
        total_in += in_tok
        total_out += out_tok

        latency = time.perf_counter() - start
        return AgenticRagResult(text, retrieved, hop, total_in, total_out, latency)


def _parse_decision(raw: str) -> dict:
    import json

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"reasoning": "fallback: could not parse decision", "retrieve_again": False, "next_query": None}


def build_agentic_rag() -> AgenticRag:
    chunks = load_chunks()
    store, embedder = build_vector_store(chunks)
    hybrid = HybridRag(store, embedder, chunks)
    return AgenticRag(hybrid)


if __name__ == "__main__":
    rag = build_agentic_rag()
    q = (
        "For a 12-year-old vehicle with a soft clutch pedal that used an "
        "Ironclad remanufactured clutch kit, what's the likely cause and "
        "what warranty term applies to the replacement part?"
    )
    result = rag.answer(q)
    print(f"Q: {q}")
    print(f"A: {result.answer}")
    print(f"hops: {result.hops}")
    print(f"retrieved from: {[c.section for c in result.retrieved]}")
    print(f"tokens in/out: {result.input_tokens}/{result.output_tokens}  "
          f"latency: {result.latency_seconds:.3f}s")
