# Torque Tune Auto Care

An MCP-based **Spare Parts Inventory Management System** for automotive
repair businesses, extended with a long-term **memory system** and a
**grounded retrieval (RAG) layer** so the same agent can also remember
customers across sessions and answer questions from internal documents
it was never given as tools.

## Overview

Torque Tune uses the **Model Context Protocol (MCP)** to expose
inventory-management tools through an MCP server: search, stock checks,
alternatives, inventory updates, and reports, all backed by a real
spare-parts database with authorization, validation, notifications,
progress reporting, and human confirmation for sensitive changes.

On top of that existing `mcp-server/` and `databases/`, this project adds
two things the base system never had:

- **Memory that survives past one session** -- a technician re-explaining
  a customer's contact preference or a prior declined repair every single
  call, because nothing the agent knew persisted once the session ended.
- **Grounded answers from documents nobody wants to turn into MCP tools**
  -- warranty terms, technical service bulletins, and diagnostic
  procedures that live in `mcp-server/resources/knowledge_base/`, not in
  the database, and that a naive "just answer from the model" approach
  would hallucinate against.

Both extensions genuinely reuse the existing `mcp-server/` and
`databases/` -- they don't duplicate them. The read/write tools, the
authorization/validation/elicitation flow, and the seeded database are
all untouched; memory and RAG sit alongside them and are wired into the
same live agent loop (`agent/client.py`).

## Features (base system)

- 🔍 Search for spare parts by name
- 📦 Check spare-part stock levels
- 🔄 Suggest alternative spare parts
- ➕ Add new spare parts
- ✏️ Update inventory quantities using increase/decrease actions
- 🗑️ Delete spare parts
- 📊 Generate inventory reports
- 🔐 Role-based authorization for inventory changes
- 🛡️ Server-side user-role lookup for inventory updates
- ✅ Inventory input validation
- 💬 MCP Elicitation for sensitive stock changes
- 🔔 Inventory notifications
- 📈 Progress tracking for inventory reports
- 🤝 MCP capability negotiation
- 👁️ Role-based tool visibility
- 🧪 Automated test suite

## Features (memory & RAG extension)

- 🧠 Short-term rolling buffer + a scratchpad distinct from it, so pruning
  the transcript never destroys the agent's active plan
- 🚦 Promote-or-drop routing: an LLM-backed (or documented mock) decision
  on short-term-memory overflow, logged with a reason per message
- 📚 Episodic memory (a persistent, chronological ledger) and semantic
  memory (versioned, consolidated facts) kept strictly separate --
  semantic memory is only ever written by a periodic consolidation pass,
  never by the router
- ♻️ Semantic consolidation with real conflict resolution, versioning,
  and expiration (see `memory/run_consolidation.py`)
- 🔎 A real vector database (HNSW ANN index + metadata payload store +
  pre-search metadata filtering) -- not a list of floats in a dict
- 🧩 Three retrieval architectures: naive RAG, hybrid (vector + BM25) RAG,
  and agentic (multi-hop) RAG
- ✅ Self-RAG-style verification on every answer: relevance-checks
  retrieved chunks, support-checks the generated answer, and refuses to
  show an unsupported answer

## MCP Tools

### Read Tools

| Tool | Description |
|---|---|
| `search_spare_part` | Search for spare parts by name. |
| `check_stock` | Return the current quantity for a spare part. |
| `suggest_alternative` | Return alternative parts for a given part ID. |
| `search_company_knowledge` | Hybrid RAG + Self-RAG-verified answer over the knowledge base (warranty terms, TSBs, diagnostic procedures, company policy). |

### Write Tools

| Tool | Description |
|---|---|
| `update_inventory` | Increase or decrease stock with authorization, validation, logging, and confirmation rules. |
| `add_spare_part` | Add a new spare part. |
| `delete_spare_part` | Delete an existing spare part. |
| `generate_inventory_report` | Generate an inventory summary while reporting progress to the client. |

## Update Inventory Flow

The `update_inventory` tool follows a controlled flow:

1. Look up the user's role from the `Users` table using `user_id`.
2. Authorize the operation based on the stored role.
3. Read the current part quantity and status.
4. Validate the requested action, quantity, status, and reason.
5. If the change is sensitive, request human confirmation through MCP Elicitation.
6. Apply the inventory update.
7. Insert an `InventoryLogs` record containing the old and new quantities, action, reason, part ID, and user ID.
8. Commit the transaction and return an inventory notification payload.

This keeps authorization and business validation on the server side rather than relying on values supplied by the client.

## Architecture

```text
Client (agent/client.py)
  │
  ▼
MCP Server (mcp-server/)
  │
  ├── Authentication & Authorization
  ├── Read Tools ─────────────────────── search_company_knowledge ──┐
  ├── Write Tools                                                   │
  ├── Validation                                                    │
  ├── Elicitation                                                   │
  ├── Notifications                                                 │
  ├── Progress Tracking                                             │
  ├── Resources (knowledge_base/*.md) ───────────────────────────── ▼
  ├── Capability Negotiation                                   rag/ (RAG layer)
  │                                                             naive / hybrid / agentic
  ▼                                                             + Self-RAG verification
SQLite / SQL Server Database (databases/)
  ├── SpareParts, Users, InventoryLogs, ...  (base system, untouched)
  └── EpisodicMemory, SemanticMemory  (memory/ writes here)

Every add_interaction() call -> memory/ (short-term buffer + scratchpad)
  └── on overflow -> promote-or-drop router -> EpisodicMemory
                                                     │
                                    memory/run_consolidation.py
                                    (separate, periodic job -- NOT
                                     called from the write path above)
                                                     ▼
                                              SemanticMemory
                                       (versioned, expiring, conflict-logged)
```

## Repository layout

```text
mcp-server/
  tools/, auth/, validation/, elicitation/, notifications/,
  progress/, resources/, negotiation/     <- base system (unchanged)
  memory/                                  <- short-term buffer, scratchpad,
                                               episodic + semantic memory,
                                               promote-or-drop router,
                                               periodic consolidation job
  rag/                                     <- chunking, embeddings, vector
                                               store, naive/hybrid/agentic
                                               RAG, Self-RAG check, the
                                               shared real-vs-mock LLM seam
  resources/knowledge_base/                <- the RAG corpus (warranty
                                               terms, TSBs, diagnostic
                                               procedures)
context_eval/          <- context-window-management strategies + test
                           transcripts + the comparison table below
retrieval_eval/         <- retrieval-architecture test questions + the
                           comparison table below
agent/                  <- the CLI client; the live, end-to-end demo
databases/               <- schema, seed data, ERD (base system)
tests/                   <- automated test suite
```

## The memory problem, and how each concern shows up

Torque Tune's longest live interactions are diagnostic/service-writer
calls: a customer states one fact early (a contact preference, a prior
declined service, a warranty detail) and the agent then spends the rest
of the call round-tripping inventory tools before a later decision
depends on that early fact. Nothing in the base `mcp-server/` tools or a
plain message buffer decides what to keep once a session runs long, or
carries anything across sessions at all -- that's the gap `memory/`
closes.

- **Short-term memory + scratchpad** (`memory/short_term_memory.py`,
  `memory/scratchpad.py`): a rolling buffer distinct from the scratchpad
  holding the agent's current plan/sub-goal/intermediate results, so
  buffer pruning never destroys active working state.
- **Promote-or-drop routing** (`memory/router.py`): fires only when the
  short-term buffer overflows. Uses the same real-Claude-or-documented-mock
  seam as the RAG layer (`rag/llm_client.py`) to decide, per message,
  promote (-> episodic memory) or drop, with a reason logged for every
  decision. Never writes to semantic memory.
- **Semantic consolidation** (`memory/semantic_memory.py`,
  `memory/run_consolidation.py`): a genuinely separate, periodic pass --
  never called from the write path above. Each run expires stale facts
  first, reads only episodes no prior pass has consolidated, extracts
  candidate facts via the LLM seam, and applies them with explicit
  versioning: a changed value is logged as a resolved conflict
  (`change_reason` + the old version kept, not deleted) rather than
  silently overwritten. Run it and see a real conflict resolved:
  ```bash
  python mcp-server/memory/run_consolidation.py
  ```
- **Vector database architecture** (`rag/vector_store.py`): a real HNSW
  ANN index (`hnswlib`) + a metadata payload store + a metadata index
  that pre-filters candidates (by `doc_type` or exact identifier) before
  similarity search runs, not just after.

## Context window management -- all four strategies

Full write-up: [`context_eval/README_SECTION.md`](context_eval/README_SECTION.md).

5 fixed long-context test transcripts (`context_eval/transcripts.py`),
each a ~35-45 message service call with one critical customer-stated fact
near the start, 14-20 tool-call/tool-output pairs burying it, and a final
question that depends on it. Run via:

```bash
python context_eval/run_eval.py
```

| Strategy | Detail recalled | Avg input tokens | Avg output tokens | Avg latency |
|---|---|---|---|---|
| Sliding window (last 10 msgs) | 0/5 | 585 | 98 | 0.0003s |
| Observation masking | 4/5 | 974 | 70 | 0.0005s |
| Recursive summarization | 4/5 | 2,216 | 202 | 0.0006s |
| Zone-based pruning | 4/5 | 974 | 70 | 0.0005s |

**Chosen: observation masking.** Sliding window fails outright because
every transcript's critical fact sits in the first few messages and is
pushed out by 14-20 tool-call pairs. Observation masking ties zone-based
pruning on recall and cost but needs only one rule (mask old tool output,
never dialogue) instead of four zone-classification rules. Recursive
summarization matches recall at ~2.3x input / ~2.9x output tokens, since
it's the only strategy making its own LLM calls to compact old chunks --
a cost that only pays off when a transcript truly can't fit in context,
which isn't Torque Tune's failure mode (long in message count, not raw
size). Full reasoning on the shared miss (T5) and the token/latency
caveat (no `ANTHROPIC_API_KEY` in this environment) is in the linked
section above.

## Retrieval architectures -- three required

Full write-up: [`retrieval_eval/README_SECTION.md`](retrieval_eval/README_SECTION.md).

9 domain-specific test questions (`retrieval_eval/test_questions.py`), 3
per category (naive-favoring general questions, hybrid-favoring exact
TSB/WT identifiers, agentic-favoring multi-part diagnostic questions).
Run via:

```bash
python retrieval_eval/run_eval.py
```

| Architecture | Answer accuracy | Top-1 retrieval accuracy | Avg input tokens | Avg output tokens | Avg latency |
|---|---|---|---|---|---|
| Naive | 7/9 | 8/9 | 479 | 123 | 0.001s |
| Hybrid | 6/9 | **9/9** | 487 | 120 | 0.002s |
| Agentic | 7/9 | **9/9** | 1,389 | 220 | 0.004s |

**Chosen: hybrid search.** Naive RAG's one miss is an embedding
confusion between two lexically similar TSB numbers -- hybrid's BM25
component fixes exactly that case at essentially the same token/latency
cost as naive. Agentic RAG matches hybrid's retrieval quality but costs
~3x the tokens and 2-4x the latency, which only pays off on genuinely
multi-hop questions. Since Torque Tune's real query mix is dominated by
single- and exact-identifier lookups, hybrid ships as the default; the
agentic path is reserved for questions that explicitly need
cross-referencing more than one document. Full reasoning, and the
"answer accuracy" vs. "top-1 retrieval accuracy" distinction (this
environment has no `ANTHROPIC_API_KEY`, so generation runs through a
documented mock), is in the linked section above.

## Self-RAG-style verification

`mcp-server/rag/self_rag_check.py` runs after every RAG answer:

1. Each retrieved chunk is checked for relevance to the question;
   irrelevant chunks are dropped before the support check.
2. The generated answer is checked for whether it's actually supported
   by the (now-filtered) retrieved context.

If either check fails, the user never sees the ungrounded answer -- they
get an explicit "I can't answer this from verified sources" message
instead. The same seam is used to verify memory recall, not just RAG
answers.

## Running the project

```bash
pip install -r requirements.txt
cp .env.example .env   # optional: add ANTHROPIC_API_KEY for real LLM calls
                        # instead of the documented mocks

# End-to-end agent demo: negotiation, tools/list, elicitation, progress,
# memory writes across the session, RAG-grounded knowledge lookup, and a
# separate periodic consolidation pass at the end
python agent/client.py

# Memory: promote-or-drop + consolidation in isolation, including a real
# resolved conflict
python mcp-server/memory/run_consolidation.py

# Evaluations that produced the tables above
python context_eval/run_eval.py
python retrieval_eval/run_eval.py

# Test suite
pytest tests/
```

Without `ANTHROPIC_API_KEY` set, the router, semantic consolidation, and
all three RAG architectures run through the documented mocks in
`mcp-server/rag/llm_client.py` -- everything above still runs end to end
and produces real (if noisier) numbers. Set the key in `.env` to re-run
with real Claude calls; nothing else needs to change.

---

## Week 4 -- Decomposition & Planning (in progress)

**Status: Issue 1 (fork + setup) and Issue 2 (task decomposition) done.**
Planning algorithms/routing, self-correction, grounded environment,
integration, eval harness, and docs/demo (Issues 3-8) not started.

**Problem:** preparing spare parts for a repair job when one or more
required parts are out of stock -- a separate agent from the memory/RAG
agent in `agent/client.py`, reusing the same `mcp-server/` and `databases/`.
Real branching (multiple valid alternative parts), real cost of a wrong
plan (reserving unavailable inventory, an incompatible substitute). Note:
this system has no supplier-availability tool (confirmed by inspection --
`Suppliers` only holds contact info), so "no part and no alternative in
stock" is a genuine dead end the plan surfaces to a human, not a step the
plan invents.

**Built on top of the reference toolkit** (not reimplemented):
github.com/AmrSheta22/task_decomposition_and_planning, vendored into
`planning/vendor/planning_lab/` -- see `planning/vendor/ATTRIBUTION.md`.

Layout:
- `planning/vendor/planning_lab/` -- the forked toolkit, unmodified
- `planning/model_provider.py` -- model-provider seam (real Claude via
  `langchain_anthropic.ChatAnthropic`, offline fallback otherwise)
- `planning/fulfillment_decomposition.py` -- decomposition-first
  (`build_plan_first`/`execute_plan_first`) and dynamic decomposition
  (`dynamic_fulfillment`), both wired to the real `search_spare_part` /
  `check_stock` / `suggest_alternative` MCP tools, not free LLM prose
- `planning/fulfillment_demo.py` -- runnable demo: `python
  planning/fulfillment_demo.py` shows the two methods diverge on a
  concrete scenario (dynamic skips an alternative-part search
  decomposition-first always pays for)
- `planning/tests/` -- cycle rejection, the vendored `Plan` model's
  8-task cap, and the divergence scenario
- `planning/SEAMS.md` -- seam-by-seam status
- `planning_eval/` -- not created yet (Issue 7)

Full write-up (why the problem is real, per-concern justification, the
comparison table) lands once the corresponding Issues (3-8) are done.
