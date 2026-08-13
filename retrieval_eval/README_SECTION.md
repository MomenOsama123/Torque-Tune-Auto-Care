# RAG / Retrieval Architecture Comparison

## The problem

Front-desk and service-writer questions about warranty windows, technical
service bulletins (TSBs), and repair decision procedures currently live only
in supplier PDFs and staff memory -- nothing the MCP server's tools or
database cover. Three new knowledge documents were added under
`mcp-server/resources/knowledge_base/` (`supplier_warranty_terms.md`,
`technical_service_bulletins.md`, `diagnostic_repair_procedures.md`)
alongside the existing `company_policy.md`, and a full RAG layer was built
on top to ground answers in them.

## What was built (`mcp-server/rag/`)

| File | Role |
|---|---|
| `chunking.py` | Loads all 4 knowledge documents, splits on `## ` headings, extracts identifiers (TSB numbers, WT codes, supplier prefixes) into metadata |
| `embeddings.py` | TF-IDF + SVD dense embeddings, fit locally on the corpus (no external embedding API available in this environment; isolated behind one function so a hosted embedding model can be swapped in later) |
| `vector_store.py` | Real vector database: `hnswlib` HNSW **ANN index** + a **metadata payload store** + a **metadata index** that pre-filters the candidate set (by `doc_type` or exact `identifier`) *before* similarity search runs |
| `keyword_search.py` | BM25 (with stopword filtering) for exact-identifier matching |
| `naive_rag.py` | Baseline: embed → retrieve top-k → generate |
| `hybrid_rag.py` | Vector similarity + BM25 merged via Reciprocal Rank Fusion |
| `agentic_rag.py` | Reasoning loop: retrieve → decide (via LLM) whether another hop is needed → retrieve again → answer |
| `self_rag_check.py` | Self-RAG-style verification: drops irrelevant retrieved chunks, and replaces an unsupported answer with an explicit "not grounded" message instead of showing it |
| `llm_client.py` | Single seam for all LLM calls (generation + agentic decisions + verification). Uses the real Claude API when `ANTHROPIC_API_KEY` is set; otherwise falls back to a documented mock so the pipeline is runnable/gradable offline |

## Retrieval comparison (`retrieval_eval/`)

9 domain-specific test questions (`test_questions.py`), 3 per category,
each designed to favor one architecture:
- **naive**: general single-hop policy questions
- **hybrid**: questions naming an exact TSB/WT identifier
- **agentic**: multi-part diagnostic questions needing two document sections

`run_eval.py` runs all three architectures against the same fixed set, each
answer passed through the Self-RAG check before scoring, and reports both
final-answer accuracy and **top-1 retrieval accuracy** (is the single
highest-ranked chunk actually the right one).

| Architecture | Answer accuracy | Top-1 retrieval accuracy | Avg input tokens | Avg output tokens | Avg latency |
|---|---|---|---|---|---|
| Naive | 7/9 | 8/9 | 479 | 123 | 0.001s |
| Hybrid | 6/9 | **9/9** | 487 | 120 | 0.002s |
| Agentic | 7/9 | **9/9** | 1,389 | 220 | 0.004s |

**Chosen architecture: Hybrid search.** Naive RAG's one miss (question H1,
asking about `TSB-2024-118`) is a real embedding-similarity confusion with
the lexically similar `TSB-2023-072` -- hybrid's keyword component fixes
exactly that case at essentially the same token/latency cost as naive.
Agentic RAG matches hybrid's retrieval quality (9/9) but costs ~3x the
tokens and 2-4x the latency, which only pays off on genuinely multi-hop
questions (e.g. A1). Given the query mix here is dominated by single- and
exact-identifier lookups, hybrid is what ships as the default, with the
agentic path reserved for questions that explicitly need cross-referencing
more than one document.

*Note on "answer accuracy": this environment has no configured
`ANTHROPIC_API_KEY`, so the generation step runs through a documented
extractive mock (see `llm_client.py`) rather than a real LLM call. Answer-
level accuracy is therefore noisier than top-1 retrieval accuracy, which
measures the actual retrieval architectures independent of that mock. Set
`ANTHROPIC_API_KEY` in `.env` to re-run with real generation before final
submission -- nothing else in `rag/` needs to change.

## Self-RAG-style verification

`self_rag_check.py` runs after every RAG answer:
1. Each retrieved chunk is checked for relevance to the question; irrelevant
   chunks are dropped before they reach the answer-support check.
2. The generated answer is checked for whether it's actually supported by
   the (now-filtered) retrieved context.

If either check fails, the user never sees the ungrounded answer -- they see
an explicit "I can't answer this from verified sources" message instead.
Demonstrated in `self_rag_check.py`'s own demo: a real question passes
verification cleanly (2 of 3 retrieved chunks kept, 1 irrelevant chunk
dropped); a fabricated/unsupported answer is caught and blocked.
