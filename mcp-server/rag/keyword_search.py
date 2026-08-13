"""
mcp-server/rag/keyword_search.py

BM25 keyword index over the same chunks stored in the vector database.
Used by hybrid_rag.py to catch exact identifiers (TSB-2024-118, WT-441,
supplier prefixes) that a dense embedding can easily blur together --
see the "Hybrid Search" slide: keyword search captures exact identifiers,
semantic search captures meaning; hybrid merges both rankings.
"""

import re

from rank_bm25 import BM25Plus

from chunking import Chunk


# Minimal stopword list. Without this, a common word like "does" or "what"
# creates spurious query/chunk overlap on chunks that share nothing else,
# which then lets BM25Plus's length-normalization floor outrank a chunk
# that actually contains the exact identifier being searched for.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "does", "do", "did", "say", "says", "said", "to", "of", "in", "on",
    "for", "and", "or", "but", "with", "about", "it", "its", "as", "at",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9-]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


class KeywordIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        corpus = [_tokenize(c.text) for c in chunks]
        self._bm25 = BM25Plus(corpus)

    def scores_for(self, query: str) -> list[float]:
        """BM25 score per chunk, same order as self.chunks, zeroed out for
        any chunk with zero token overlap with the query.

        BM25Plus adds a floor delta so it still assigns a nonzero (and,
        for very short chunks, sometimes even a *higher*) score to chunks
        that share no term with the query at all -- that's the length-
        normalization smoothing it needs to handle real corpora, but on
        a small corpus of short chunks it actively misranks non-matches
        above true matches. Zeroing non-overlapping chunks keeps BM25's
        actual job (ranking among true matches) without that artifact.
        """
        tokens = _tokenize(query)
        query_token_set = set(tokens)
        raw_scores = self._bm25.get_scores(tokens)

        scores = []
        for chunk, score in zip(self.chunks, raw_scores):
            overlap = query_token_set & set(_tokenize(chunk.text))
            scores.append(float(score) if overlap else 0.0)
        return scores
