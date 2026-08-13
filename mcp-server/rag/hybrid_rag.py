"""
mcp-server/rag/hybrid_rag.py

Hybrid search: Semantic Search + Keyword Search -> Merged Ranking (see the
"Hybrid Search" slide). Keyword search captures exact identifiers like
TSB-2024-118 or a WT-xxx code that a small local embedding can blur
together with lexically-similar-but-wrong chunks (see naive_rag.py's demo
query for TSB-2024-118, which pulled in TSB-2023-072 as a false match).

Merge strategy: reciprocal rank fusion (RRF) across the two independently
ranked lists. RRF is simple, needs no score normalization between BM25 and
cosine similarity (which live on different scales), and is the standard
lightweight way to combine heterogeneous rankers.
"""

import time
from dataclasses import dataclass

from chunking import Chunk, load_chunks
from embeddings import Embedder
from keyword_search import KeywordIndex
from llm_client import llm_call
from naive_rag import PROMPT_TEMPLATE, RagResult
from vector_store import VectorStore, build_vector_store

RRF_K = 60  # standard RRF damping constant


class HybridRag:
    def __init__(self, store: VectorStore, embedder: Embedder, chunks: list[Chunk]):
        self.store = store
        self.embedder = embedder
        self.chunks = chunks
        self.keyword_index = KeywordIndex(chunks)

    def _vector_ranked_ids(self, question: str, pool: int) -> list[int]:
        qvec = self.embedder.embed([question])[0]
        matches = self.store.query(qvec, top_k=pool)
        return [self.chunks.index(m.chunk) for m in matches]

    def _keyword_ranked_ids(self, question: str, pool: int) -> list[int]:
        scores = self.keyword_index.scores_for(question)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return ranked[:pool]

    def _merged_ranking(self, question: str, top_k: int) -> list[int]:
        pool = max(top_k * 3, 6)
        vec_ids = self._vector_ranked_ids(question, pool)
        kw_ids = self._keyword_ranked_ids(question, pool)

        rrf_scores: dict[int, float] = {}
        for rank, idx in enumerate(vec_ids):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, idx in enumerate(kw_ids):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)

        ranked = sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)
        return ranked[:top_k]

    def answer(self, question: str, top_k: int = 3) -> RagResult:
        start = time.perf_counter()

        ids = self._merged_ranking(question, top_k)
        retrieved = [self.chunks[i] for i in ids]

        context = "\n\n---\n\n".join(c.text for c in retrieved)
        prompt = PROMPT_TEMPLATE.format(context=context, question=question)
        text, in_tok, out_tok = llm_call(system="You are a precise assistant.", user=prompt)

        latency = time.perf_counter() - start
        return RagResult(text, retrieved, in_tok, out_tok, latency)


def build_hybrid_rag() -> HybridRag:
    chunks = load_chunks()
    store, embedder = build_vector_store(chunks)
    return HybridRag(store, embedder, chunks)


if __name__ == "__main__":
    rag = build_hybrid_rag()
    q = "What does TSB-2024-118 say?"
    result = rag.answer(q)
    print(f"Q: {q}")
    print(f"A: {result.answer}")
    print(f"retrieved from: {[c.section for c in result.retrieved]}")
    print(f"tokens in/out: {result.input_tokens}/{result.output_tokens}  "
          f"latency: {result.latency_seconds:.3f}s")
