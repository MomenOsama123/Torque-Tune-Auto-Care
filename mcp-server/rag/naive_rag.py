"""
mcp-server/rag/naive_rag.py

The baseline pipeline from the "The RAG Pipeline" slide:
Documents -> Chunking -> Embeddings -> Vector Database -> User Query ->
Embedding -> Retrieve Top-K -> Prompt -> LLM -> Answer.

No keyword matching, no multi-hop reasoning -- one embed, one retrieve,
one generate. This is the architecture the retrieval_eval comparison
table uses as the floor every other architecture is measured against.
"""

import time
from dataclasses import dataclass

from chunking import Chunk, load_chunks
from embeddings import Embedder
from llm_client import llm_call
from vector_store import VectorStore, build_vector_store

PROMPT_TEMPLATE = """Answer using only this context. If the context does not \
contain the answer, say so explicitly -- never guess.

Context:
{context}

Question:
{question}"""


@dataclass
class RagResult:
    answer: str
    retrieved: list[Chunk]
    input_tokens: int
    output_tokens: int
    latency_seconds: float


class NaiveRag:
    def __init__(self, store: VectorStore, embedder: Embedder):
        self.store = store
        self.embedder = embedder

    def answer(self, question: str, top_k: int = 3) -> RagResult:
        start = time.perf_counter()

        qvec = self.embedder.embed([question])[0]
        matches = self.store.query(qvec, top_k=top_k)
        retrieved = [m.chunk for m in matches]

        context = "\n\n---\n\n".join(c.text for c in retrieved)
        prompt = PROMPT_TEMPLATE.format(context=context, question=question)
        text, in_tok, out_tok = llm_call(system="You are a precise assistant.", user=prompt)

        latency = time.perf_counter() - start
        return RagResult(text, retrieved, in_tok, out_tok, latency)


def build_naive_rag() -> NaiveRag:
    chunks = load_chunks()
    store, embedder = build_vector_store(chunks)
    return NaiveRag(store, embedder)


if __name__ == "__main__":
    rag = build_naive_rag()
    for q in [
        "What's the warranty window on remanufactured Ironclad clutch kits?",
        "What does TSB-2024-118 say?",
    ]:
        result = rag.answer(q)
        print(f"Q: {q}")
        print(f"A: {result.answer}")
        print(f"retrieved from: {[c.section for c in result.retrieved]}")
        print(f"tokens in/out: {result.input_tokens}/{result.output_tokens}  "
              f"latency: {result.latency_seconds:.3f}s\n")
