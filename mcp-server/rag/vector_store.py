"""
mcp-server/rag/vector_store.py

Step 2b of the RAG pipeline: a real vector database replacement using NumPy,
avoiding the need for native C++ build tools (hnswlib).

Three components:
    1. Vector Index    -> NumPy matrix storage (Cosine similarity via Dot Product)
    2. Metadata Store  -> self._payloads  (chunk text + metadata, keyed by id)
    3. Metadata Index  -> self._metadata_index (inverted index: field value
                          -> set of internal ids), used to PRE-filter the
                          candidate set before similarity search runs.
"""

from dataclasses import dataclass
import numpy as np

from chunking import Chunk
from embeddings import Embedder


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float  # cosine similarity, higher = more similar


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self._next_id = 0
        self._payloads: dict[int, Chunk] = {}           # Metadata (payload) store
        self._metadata_index: dict[str, set[int]] = {}  # field:value -> {ids}
        self._vectors: dict[int, np.ndarray] = {}       # internal_id -> vector array

    # ---- indexing -------------------------------------------------
    def upsert(self, chunk: Chunk, vector: np.ndarray) -> int:
        internal_id = self._next_id
        self._next_id += 1

        # L2-normalize the vector for easy Cosine Similarity via Dot Product
        v = np.array(vector, dtype=np.float32).flatten()
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm

        self._vectors[internal_id] = v
        self._payloads[internal_id] = chunk

        # Build the metadata index: one entry per filterable field/value.
        self._add_to_metadata_index("doc_type", chunk.doc_type, internal_id)
        self._add_to_metadata_index("source", chunk.source, internal_id)
        for ident in chunk.identifiers:
            self._add_to_metadata_index("identifier", ident, internal_id)

        return internal_id

    def _add_to_metadata_index(self, field: str, value: str, internal_id: int) -> None:
        key = f"{field}:{value}"
        self._metadata_index.setdefault(key, set()).add(internal_id)

    # ---- candidate pre-filtering -----------------------------------
    def _filtered_candidate_ids(self, filters: dict[str, str] | None) -> set[int] | None:
        """Returns None if no filter (search everything), else the set of
        internal ids matching ALL given filters -- computed purely from
        the metadata index, before any vector math happens."""
        if not filters:
            return None
        candidate_sets = []
        for field, value in filters.items():
            key = f"{field}:{value}"
            candidate_sets.append(self._metadata_index.get(key, set()))
        if not candidate_sets:
            return set()
        result = candidate_sets[0].copy()
        for s in candidate_sets[1:]:
            result = result & s
        return result

    # ---- querying ---------------------------------------------------
    def query(
        self,
        query_vector: np.ndarray,
        top_k: int = 3,
        filters: dict[str, str] | None = None,
    ) -> list[ScoredChunk]:
        candidate_ids = self._filtered_candidate_ids(filters)

        # Determine which internal IDs to search
        if candidate_ids is not None:
            if not candidate_ids:
                return []
            ids = sorted(candidate_ids)
        else:
            if not self._vectors:
                return []
            ids = sorted(self._vectors.keys())

        # Prepare normalized query vector
        q = np.array(query_vector, dtype=np.float32).flatten()
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        # Matrix dot product for Cosine Similarity
        matrix = np.stack([self._vectors[i] for i in ids])
        sims = matrix @ q

        # Rank and return top_k
        ranked = sorted(zip(ids, sims), key=lambda x: x[1], reverse=True)[:top_k]
        return [ScoredChunk(self._payloads[i], float(s)) for i, s in ranked]

    def _get_vector(self, internal_id: int) -> np.ndarray:
        return self._vectors[internal_id]


def build_vector_store(chunks: list[Chunk]) -> tuple[VectorStore, Embedder]:
    embedder = Embedder()
    embedder.fit([c.text for c in chunks])
    vectors = embedder.embed([c.text for c in chunks])

    store = VectorStore(dim=embedder.dim)
    for chunk, vector in zip(chunks, vectors):
        store.upsert(chunk, vector)
    return store, embedder


if __name__ == "__main__":
    from chunking import load_chunks

    all_chunks = load_chunks()
    store, embedder = build_vector_store(all_chunks)

    print("--- Unfiltered search ---")
    q = "is my alternator still under warranty"
    qvec = embedder.embed([q])[0]
    for r in store.query(qvec, top_k=3):
        print(f"  {r.score:.3f}  [{r.chunk.doc_type}] {r.chunk.section}")

    print("\n--- Metadata-filtered search (doc_type=warranty only) ---")
    for r in store.query(qvec, top_k=3, filters={"doc_type": "warranty"}):
        print(f"  {r.score:.3f}  [{r.chunk.doc_type}] {r.chunk.section}")

    print("\n--- Metadata-filtered search (exact identifier=TSB-2024-118) ---")
    q2 = "clutch pedal soft after install"
    qvec2 = embedder.embed([q2])[0]
    for r in store.query(qvec2, top_k=3, filters={"identifier": "TSB-2024-118"}):
        print(f"  {r.score:.3f}  [{r.chunk.doc_type}] {r.chunk.section}")
