"""
mcp-server/rag/embeddings.py

Step 2a of the RAG pipeline: turn each chunk's text into a dense vector.

Design decision -- why TF-IDF + SVD instead of a hosted embedding API:
This lab environment has no network access to an embedding provider
(OpenAI, Voyage, Cohere, etc.) and no way to download a pretrained
sentence-transformer model. TF-IDF + Truncated SVD (i.e. classic LSA) is
a legitimate, fully-local way to produce dense vectors where semantically
related chunks end up close together in vector space -- it is fit
directly on this corpus, needs no external calls, and is deterministic.

This is intentionally isolated behind one `embed_texts()` function. In a
real deployment, swap the body of this function for a call to a hosted
embedding model (e.g. `client.embeddings.create(...)`) -- nothing else in
vector_store.py, naive_rag.py, hybrid_rag.py, or agentic_rag.py needs to
change, since they only depend on this function's input/output shape:
list[str] -> list[list[float]].
"""

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

EMBEDDING_DIM = 64


class Embedder:
    """Fit once on the full corpus, then embed queries/chunks with the
    same fitted vectorizer + SVD so everything lands in one vector space."""

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim
        self._tfidf = TfidfVectorizer(
            token_pattern=r"[a-zA-Z0-9_./%-]+",  # keep identifiers like TSB-2024-118 intact
            ngram_range=(1, 2),
        )
        # n_components can't exceed n_samples/n_features - 1; clamp later in fit().
        self._svd = TruncatedSVD(n_components=dim, random_state=0)
        self._fitted = False

    def fit(self, corpus_texts: list[str]) -> None:
        n_components = min(self.dim, max(2, len(corpus_texts) - 1))
        if n_components != self.dim:
            self._svd = TruncatedSVD(n_components=n_components, random_state=0)
            self.dim = n_components
        tfidf_matrix = self._tfidf.fit_transform(corpus_texts)
        self._svd.fit(tfidf_matrix)
        self._fitted = True

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Embedder.fit() must be called on the corpus first.")
        tfidf_matrix = self._tfidf.transform(texts)
        dense = self._svd.transform(tfidf_matrix)
        # L2-normalize so cosine similarity == dot product (what hnswlib's
        # 'cosine' space expects for well-behaved nearest-neighbor search).
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return dense / norms


if __name__ == "__main__":
    from chunking import load_chunks

    chunks = load_chunks()
    embedder = Embedder()
    embedder.fit([c.text for c in chunks])
    vecs = embedder.embed([c.text for c in chunks[:3]])
    print(f"Fitted on {len(chunks)} chunks -> embedding dim = {embedder.dim}")
    print(f"Sample embedding shape: {vecs.shape}")
    print(f"First vector, first 8 dims: {vecs[0][:8]}")
