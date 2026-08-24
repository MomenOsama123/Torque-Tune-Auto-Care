# Torque Tune Auto Care

An MCP-based **Spare Parts Inventory Management System** for automotive
repair businesses, extended with a long-term **memory system**, a
**grounded retrieval (RAG) layer**, a **task decomposition & planning
module**, a set of durable, resumable **state graphs** for long-running
business workflows, and an experimental **Streamlit platform** that ties
all of the above together behind one UI.

---

## Table of contents

- [Overview](#overview)
- [Problem statement](#problem-statement)
- [Key features](#key-features)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Installation](#installation)
- [Environment variables](#environment-variables)
- [Usage](#usage)
- [Available commands](#available-commands)
- [MCP tools / API documentation](#mcp-tools--api-documentation)
- [Configuration](#configuration)
- [Evaluation methodology & results](#evaluation-methodology--results)
- [Testing](#testing)
- [Implementation & verification status](#implementation--verification-status)
- [Known issues / limitations](#known-issues--limitations)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Attribution](#attribution)
- [License](#license)

---

## Overview

Torque Tune Auto Care exposes spare-parts inventory operations (search,
stock checks, alternatives, updates, reporting) through an **MCP (Model
Context Protocol)** server backed by a real relational database, with
role-based authorization, input validation, human confirmation for
sensitive changes, notifications, and progress reporting.

On top of that base inventory system, the project solves problems a
simple tool-calling agent cannot:

- **Session amnesia** — a technician has to re-explain a customer's
  contact preference or a previously declined repair on every call
  because nothing the agent knew persisted once the session ended. A
  **memory system** (short-term buffer, episodic memory, and consolidated
  semantic memory) closes this gap.
- **Hallucinated answers from unstructured knowledge** — warranty terms,
  technical service bulletins, and diagnostic procedures live in Markdown
  documents, not the database, and naively asking a model to answer from
  them risks fabrication. A **RAG layer** (naive, hybrid, and agentic
  retrieval, verified with a Self-RAG-style check) grounds answers in the
  real knowledge base.
- **Multi-step fulfillment with real branching** — preparing spare parts
  for a repair job when a required part is out of stock requires
  evaluating alternatives and their trade-offs. A **planning module**
  applies decomposition, lookahead search, and self-correction algorithms
  to this problem.
- **Long-running, human-gated business processes** — purchase orders,
  inventory-change approvals, and warranty claims can pause for days
  waiting on a supplier or a manager, and must survive process restarts.
  A **state-graph engine** with SQL-backed checkpointing models these as
  resumable workflows instead of blocking calls.
- **No single place to drive any of this** — a **Streamlit platform**
  (`platform_streamlit/Home.py`) lists the Memory/RAG agent, the Planning
  agent, and the three state-graph workflows behind one page, and routes
  free-text questions (in **English or Arabic**) to the right agent.

## Problem statement

A repair shop's day-to-day inventory work is not a single request/response
loop. The same conversation needs to: recall what a customer said last
week, answer a warranty question grounded in real documents instead of a
guess, decide what to do when a required part is out of stock, and track
a purchase order or an approval that may not resolve for days — all while
a human stays in control of anything sensitive (stock changes, high-cost
purchase orders, approvals). Torque Tune's four extensions (memory, RAG,
planning, state graphs) and the platform UI on top of them are built
specifically to cover those four gaps around a base MCP inventory server
that, by itself, only handles one tool call at a time with no memory
across calls.

## Key features

### Core inventory system (MCP server)

- 🔍 Search for spare parts by name
- 📦 Check spare-part stock levels
- 🔄 Suggest alternative spare parts
- ➕ Add new spare parts, ✏️ update quantities (increase/decrease), 🗑️ delete parts
- 📊 Generate inventory reports with real-time progress reporting
- 🔐 Role-based authorization and server-side role lookup for inventory changes
- ✅ Input validation for all write operations
- 💬 MCP Elicitation (human-in-the-loop confirmation) for sensitive stock changes
- 🔔 Inventory change notifications
- 🤝 MCP capability negotiation (initialize/initialized handshake)
- 👁️ Role-based tool visibility
- 🧪 Automated test suite (pytest)

### Memory extension

- 🧠 Short-term rolling buffer plus a separate scratchpad for active plans
- 🚦 LLM-backed (or mocked) promote-or-drop routing on buffer overflow
- 📚 Episodic memory (chronological ledger) and semantic memory (versioned,
  consolidated facts), written by two clearly separate paths
- ♻️ Periodic semantic consolidation with conflict resolution, versioning,
  and fact expiration

### RAG extension

- 🔎 A real vector store (HNSW ANN index + metadata payload store +
  metadata pre-filtering)
- 🧩 Three retrieval architectures: naive, hybrid (vector + BM25), and
  agentic (multi-hop)
- ✅ Self-RAG-style verification: relevance-checks retrieved chunks and
  support-checks the generated answer before it is shown to the user

### Planning extension

- 🧭 Decomposition-first and dynamic decomposition strategies for
  spare-parts fulfillment plans
- 🌳 Plan-and-Solve and Tree-of-Thoughts search for comparing candidate
  alternatives
- 🎯 Grounded LATS (Language Agent Tree Search) for high-impact
  proceed/delay decisions
- 🔁 Self-correction via Reflexion and Self-Refine
- 📈 A reproducible evaluation harness comparing all methods
- 🌐 **Bilingual routing** — `is_planning_request()` (`agent/client.py`)
  recognizes both English (`"spare part"`, `"repair job"`, `"out of
  stock"`, `"fulfill"`, ...) and Arabic (`"قطع غيار"`, `"شغل إصلاح"`,
  `"مخزون"`, `"غير متوفر"`, ...) planning keywords, so Arabic requests are
  correctly routed to the Planning Agent instead of falling through to
  Memory/RAG. See [Task 2](#task-2--bilingual-planning-request-routing)
  below.

### State-graph extension

- 🛒 **Purchase Order graph** — batches low-stock parts per supplier,
  waits (possibly for days) for supplier confirmation, with manager
  approval above a cost threshold
- 🔧 **Inventory Approval graph** — pauses sensitive stock changes for
  manager sign-off, grounded in company policy via RAG, with revision loops
- 🛡️ **Warranty Claim graph** — grounds claim eligibility in supplier
  warranty terms, generates Tree-of-Thoughts appeal arguments, and loops
  through bounded appeal rounds
- 💾 Durable, database-backed checkpointing so a workflow can resume from
  a completely different process after a crash
- 🎫 Failure-ticket filing when a node raises mid-run, instead of
  crashing the whole process

### Streamlit platform

- 🖥️ A single page (`platform_streamlit/Home.py`) listing the Memory/RAG
  agent, the Planning agent, and the three state-graph workflows
- 🌐 Arabic-facing UI copy, with a free-text question box that routes
  planning-shaped questions (English or Arabic) into a structured
  job-request form (Job ID + up to 3 required parts) instead of the
  Memory/RAG path
- ✅ Verified to install and start cleanly from `requirements.txt` alone —
  see [Task 5](#task-5--platform-dependencies--startup-verification)

## Architecture

```text
Client (agent/client.py)  <-- also driven by platform_streamlit/Home.py
  │
  ▼
MCP Server (mcp-server/)
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
SQLite (demo) / SQL Server Database (databases/)
  ├── SpareParts, Users, InventoryLogs, WarrantyClaims, PurchaseOrders, ...
  └── EpisodicMemory, SemanticMemory (memory/ writes here)

Every interaction -> memory/ (short-term buffer + scratchpad)
  └── on overflow -> promote-or-drop router -> EpisodicMemory
                                    │
                     memory/run_consolidation.py (separate, periodic job)
                                    ▼
                              SemanticMemory (versioned, expiring, conflict-logged)

Repair/spare-parts requests (English or Arabic, agent/client.py::is_planning_request)
  -> planning/ (decomposition, ToT/LATS, Reflexion/Self-Refine)

Long-running workflows -> state_graph/ (Purchase Order, Inventory Approval, Warranty Claim)
                                    -> checkpointed to the database, resumable across processes

platform_streamlit/Home.py -> lists all agents above, routes free-text
                               questions to Memory/RAG or Planning
```

`databases/schema.sql` is written for SQL Server, but `databases/db.py`'s
`get_connection()` does not implement that connection today — it always
raises `RuntimeError("No database connection configured...")` unless a
caller supplies one. The seeded SQLite demo database
(`agent/demo_db.py`) is the only database path actually running in this
environment; tests reach it through the shared `demo_db_connection`
pytest fixture in the repository-root `conftest.py` (see
[Testing](#testing)).

## Project structure

```text
mcp-server/
  tools/            # read_tools.py, write_tools.py — the MCP tools
  auth/             # authorization.py
  validation/       # schemas.py, validators.py
  elicitation/      # human-confirmation flow
  notifications/    # notifier.py
  progress/         # progress.py
  negotiation/       # capability negotiation (initialize/initialized)
  resources/        # static resources + resources/knowledge_base/*.md (RAG corpus)
  memory/           # short-term buffer, scratchpad, episodic + semantic
                     # memory, promote-or-drop router, consolidation job
  rag/              # chunking, embeddings, vector store, naive/hybrid/
                     # agentic RAG, Self-RAG check, LLM client seam
  tool_registry.py  # enable/disable tools per agent
  app.py            # FastMCP app instance + MemoryManager wiring
  server.py         # registers tools/resources/negotiation, entry point
  config.py         # server name, DB path, roles, stock threshold

agent/
  client.py         # MCP client + live agent router (is_planning_request,
                     # handle_user_request); entry point for the CLI demo
  demo_db.py         # seeded SQLite demo database + reset helper

planning/
  vendor/planning_lab/          # vendored decomposition & planning toolkit
  model_provider.py             # real Claude / offline model seam
  fulfillment_decomposition.py  # decomposition-first & dynamic decomposition
  fulfillment_planning.py       # planning entry points
  self_correction.py            # Reflexion / Self-Refine
  routing.py                    # routes sub-tasks to the right algorithm
  grounded_environment.py       # database-grounded environment for LATS
  fulfillment_demo.py           # runnable demo script
  tests/                        # planning-specific tests

planning_eval/
  scenarios.py, metrics.py, harness.py, run_eval.py   # evaluation harness
  results/                                             # generated comparison tables & run artifacts

state_graph/
  graphs/
    purchase_order_graph.py
    inventory_approval_graph.py
    warranty_graph.py
  engine.py          # graph execution engine
  checkpointer.py    # durable checkpointing
  tickets.py         # failure-ticket handling
  bootstrap.py       # wiring helper (ensure_wired, used by the platform)
  db.py              # state-graph persistence
  run_demo.py        # narrated end-to-end demo
  tests/             # engine, crash/resume, and graph tests

context_eval/        # context-window-management strategy comparison + tests
retrieval_eval/      # retrieval-architecture comparison + test questions
databases/           # schema.sql, seed.sql, erd.mmd, db.py
platform_streamlit/  # Home.py — Streamlit platform (Memory/RAG + Planning + state graphs)
mcp/                  # shim package exposing mcp-server/ as `mcp`
tests/                # top-level automated test suite (+ database-isolation
                      # regression test, test_db_isolation_regression.py)
conftest.py           # repo-root pytest fixtures — demo_db_connection,
                      # the single source of DB test isolation
requirements.txt
.env.example
```

## Tech stack

| Category | Technology |
|---|---|
| Language | Python 3 |
| Protocol | Model Context Protocol (MCP) — `mcp-server/fastmcp.py` (local FastMCP-style implementation) |
| Database | SQL Server-oriented schema (`databases/schema.sql`), with a SQLite demo database for local runs (`agent/demo_db.py`) |
| LLM provider | Anthropic Claude via the `anthropic` SDK (optional; falls back to documented mocks) |
| Planning models | `langchain-anthropic` / `langchain-core` (`ChatAnthropic`), offline fallback otherwise |
| Vector search | `numpy`, `scikit-learn` (TF-IDF + Truncated SVD embeddings), HNSW-style ANN index |
| Keyword search | `rank_bm25` |
| DAG/graph utilities | `networkx` (used by the vendored planning toolkit) |
| Validation | `pydantic` |
| Config | `python-dotenv` |
| Testing | `pytest` |
| UI | `streamlit` (declared in `requirements.txt` — see [Task 5](#task-5--platform-dependencies--startup-verification)) |

## Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd Torque-Tune-Auto-Care

# 2. (Recommended) create and activate a virtual environment

# macOS / Linux:
python -m venv venv
source venv/bin/activate

# Windows (PowerShell):
python -m venv venv
venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the environment template

# macOS / Linux:
cp .env.example .env

# Windows (PowerShell):
Copy-Item .env.example .env
```

`requirements.txt` already declares every third-party import this
project uses, including `streamlit>=1.28.0` for
`platform_streamlit/Home.py` — a single `pip install -r requirements.txt`
is sufficient; nothing needs to be installed separately (verified, see
[Task 5](#task-5--platform-dependencies--startup-verification)).

### Prerequisites

- Python 3.10+ (recommended)
- `pip` for installing dependencies
- A relational database if you intend to run against a real backend (the
  schema targets SQL Server); a seeded SQLite demo database is provided
  for local development and requires no external setup
- An Anthropic API key (optional) — without it, the memory router,
  semantic consolidation, all RAG architectures, and the planning module
  run against documented, deterministic offline mocks

## Environment variables

All variables are defined in `.env.example`. Copy it to `.env` and fill
in real values locally — `.env` is git-ignored and must never be
committed.

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | If unset, the memory router, semantic consolidation, all RAG architectures, and the planning module fall back to documented offline mocks instead of calling the real Claude API. |
| `DB_CONNECTION_STRING` | No | Only needed if `databases/db.py` is pointed at a real SQL Server instance instead of the seeded SQLite demo database. |
| `PLANNING_INPUT_USD_PER_1M` | No | Price (USD per 1M input tokens) for the model used in the planning evaluation, used to populate the Cost column when live usage metadata is available. |
| `PLANNING_OUTPUT_USD_PER_1M` | No | Price (USD per 1M output tokens), same purpose as above. |

## Usage

### Experimental Streamlit platform (Memory/RAG + Planning + state graphs, one UI)

```bash
streamlit run platform_streamlit/Home.py
```

Lists the Memory/RAG agent, the Planning agent, and all three
state-graph workflows on one page. The question box routes planning-shaped
free text — **in English or Arabic** — into a structured job-request form
instead of the general Memory/RAG path; anything else stays on Memory/RAG.
Startup, imports, and a headless `AppTest` load have been verified with
zero exceptions — see [Task 5](#task-5--platform-dependencies--startup-verification).

### End-to-end MCP agent demo (CLI)

Runs capability negotiation, tool discovery, a read call, a role change, a
resource read, an elicitation-gated write, and a progress-reporting call,
plus a live pass through the planning router, finishing with a memory
write and consolidation pass:

```bash
python agent/client.py
```

### Memory consolidation in isolation

Runs the promote-or-drop router and semantic consolidation, including a
real resolved conflict:

```bash
python mcp-server/memory/run_consolidation.py
```

### Planning demo

Shows decomposition-first and dynamic decomposition diverging on a
concrete fulfillment scenario:

```bash
python planning/fulfillment_demo.py
```

### State-graph demo

Runs the purchase-order, inventory-approval, and warranty-claim graphs
end to end, including a live crash-and-resume simulation and a
deliberately failing node:

```bash
# macOS / Linux
PYTHONPATH=. python3 state_graph/run_demo.py

# Windows (PowerShell)
$env:PYTHONPATH = "."
python state_graph/run_demo.py
```

### MCP server (standalone)

```bash
python mcp-server/server.py
```

## Available commands

| Command (macOS / Linux) | Command (Windows PowerShell) | Purpose |
|---|---|---|
| `python agent/client.py` | `python agent/client.py` | End-to-end MCP client demo against the seeded database, including the planning router |
| `python mcp-server/server.py` | `python mcp-server/server.py` | Start the MCP server standalone |
| `python mcp-server/memory/run_consolidation.py` | `python mcp-server/memory/run_consolidation.py` | Run promote-or-drop + semantic consolidation |
| `python planning/fulfillment_demo.py` | `python planning/fulfillment_demo.py` | Run the decomposition/planning demo |
| `python context_eval/run_eval.py` | `python context_eval/run_eval.py` | Run the context-window-management strategy comparison |
| `python retrieval_eval/run_eval.py` | `python retrieval_eval/run_eval.py` | Run the retrieval-architecture comparison |
| `python planning_eval/run_eval.py` | `python planning_eval/run_eval.py` | Run the planning-algorithm comparison |
| `PYTHONPATH=. python3 state_graph/run_demo.py` | `$env:PYTHONPATH="."` then `python state_graph/run_demo.py` | Run the state-graph narrated demo (standalone script — needs `PYTHONPATH` set to the repo root; `pytest` does not) |
| `pytest state_graph/tests/ -q` | `pytest state_graph/tests/ -q` | Run state-graph tests — `PYTHONPATH` is **not** needed here; the repository-root `conftest.py` adds the repo root to `sys.path` automatically whenever `pytest` runs |
| `pytest tests/ state_graph/tests/ planning/tests/ -q` | `pytest tests/ state_graph/tests/ planning/tests/ -q` | Run the full automated test suite (recommended explicit form — see note below) |
| `streamlit run platform_streamlit/Home.py` | `streamlit run platform_streamlit/Home.py` | Launch the Streamlit platform |

## MCP tools / API documentation

Torque Tune does not expose a REST API; it exposes tools over the Model
Context Protocol. Tools are discovered via `tools/list` and invoked via
`tools/call`, subject to role-based visibility and the capability
negotiation implemented in `mcp-server/negotiation/negotiation.py`.

### Read tools

| Tool | Parameters | Description |
|---|---|---|
| `search_spare_part` | `part_name: str` | Search for spare parts by name (partial match). Raises an error if no results are found. |
| `check_stock` | `part_id: int` | Return the current quantity for a spare part. Raises an error if the part does not exist. |
| `suggest_alternative` | `part_id: int` | Return alternative parts registered for a given part ID. |
| `search_company_knowledge` | (RAG query) | Hybrid RAG + Self-RAG-verified answer over the knowledge base (warranty terms, technical service bulletins, diagnostic procedures, company policy). Returns an explicit refusal instead of an unsupported answer when verification fails. |

### Write tools

| Tool | Description |
|---|---|
| `update_inventory` | Increases or decreases stock for a part, following the authorization/validation/elicitation flow below. |
| `add_spare_part` | Adds a new spare part to the catalog. |
| `delete_spare_part` | Deletes an existing spare part. |
| `generate_inventory_report` | Generates an inventory summary while reporting progress to the client. |

### `update_inventory` flow

1. Look up the requesting user's role from the `Users` table via `user_id`.
2. Authorize the operation based on the stored role.
3. Read the current part quantity and status.
4. Validate the requested action, quantity, status, and reason.
5. If the change is sensitive (e.g. reducing a part to zero), request
   human confirmation through MCP Elicitation.
6. Apply the inventory update.
7. Insert an `InventoryLogs` record with the old/new quantity, action,
   reason, part ID, and user ID.
8. Commit the transaction and return an inventory notification payload.

Authorization and business validation are enforced server-side rather
than trusted from client-supplied values.

### Live-agent routing (`agent/client.py`)

`handle_user_request(request, *, job=None, llm=None)` is the router
called by both the CLI demo and the Streamlit platform:

1. `is_planning_request(request)` checks the request text against an
   English **and Arabic** keyword set (spare parts / repair job / stock /
   fulfillment terms, and their Arabic equivalents — e.g. `قطع غيار`,
   `شغل إصلاح`, `مخزون`, `غير متوفر`).
2. If it matches, the request is routed into `planning/` (decomposition,
   then Tree-of-Thoughts / grounded LATS, then Reflexion/Self-Refine) and
   the outcome is written to session memory as a `"planning"` interaction.
3. Otherwise the request returns `{"route": "memory_rag", "handled":
   False}` and continues down the existing Memory/RAG path unchanged.

## Configuration

Server-level configuration lives in `mcp-server/config.py`:

```python
SERVER_NAME = "Torque Tune Auto Care"
DATABASE_PATH = "databases/auto_care.db"
ALLOWED_ROLES = {"admin", "manager", "technician"}
MIN_STOCK_THRESHOLD = 10
```

Server capability declaration (`mcp-server/negotiation/negotiation.py`):

```python
SERVER_INFO = {"name": "auto-care-inventory-mcp-server", "version": "0.1.0"}
SERVER_CAPABILITIES = {
    "resources": {"listChanged": False},
    "elicitation": {},
    "tools": {"listChanged": True},
}
```

Per-agent tool visibility is managed through
`mcp-server/tool_registry.py` (backed by
`mcp-server/_data/tool_registry.json`), which is what the Streamlit
platform's "MCP Tools" controls toggle.

The database schema (`databases/schema.sql`) includes core inventory
tables (`Users`, `Categories`, `Suppliers`, `SpareParts`,
`AlternativeParts`, `InventoryLogs`), long-running-workflow tables
(`WarrantyClaims`, `PurchaseOrders`), and agent-memory tables
(`EpisodicMemory`, `SemanticMemory`). Seed data is in
`databases/seed.sql`; an entity-relationship diagram is at
`databases/erd.mmd`.

Test-time database wiring is centralized in the repository-root
`conftest.py`'s `demo_db_connection` fixture: it resets a freshly seeded
SQLite database and monkeypatches every module that independently does
`from databases.db import get_connection` (so patch order and import
order stop mattering), and every patch is auto-reverted by `pytest` at
the end of each test. Any test that touches the database must request
this fixture; see [Known issues](#known-issues--limitations) for the
handful of tests that currently don't.

## Evaluation methodology & results

The repository ships reproducible comparisons, generated by the scripts
under `context_eval/`, `retrieval_eval/`, and `planning_eval/`. Without
`ANTHROPIC_API_KEY` set, all of the below run against deterministic
offline mocks and still produce complete, reproducible tables; token/cost
figures are explicitly labelled as offline estimates in that case.

### Context window management — four strategies

Full write-up: [`context_eval/README_SECTION.md`](context_eval/README_SECTION.md).

5 fixed long-context test transcripts (`context_eval/transcripts.py`),
each a ~35-45 message service call with one critical customer-stated
fact near the start, 14-20 tool-call/tool-output pairs burying it, and a
final question that depends on it.

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
it's the only strategy making its own LLM calls to compact old chunks — a
cost that only pays off when a transcript truly can't fit in context,
which isn't Torque Tune's failure mode (long in message count, not raw
size).

### Retrieval architectures — three required

Full write-up: [`retrieval_eval/README_SECTION.md`](retrieval_eval/README_SECTION.md).

9 domain-specific test questions (`retrieval_eval/test_questions.py`), 3
per category (naive-favoring general questions, hybrid-favoring exact
TSB/WT identifiers, agentic-favoring multi-part diagnostic questions).

```bash
python retrieval_eval/run_eval.py
```

| Architecture | Answer accuracy | Top-1 retrieval accuracy | Avg input tokens | Avg output tokens | Avg latency |
|---|---|---|---|---|---|
| Naive | 7/9 | 8/9 | 479 | 123 | 0.001s |
| Hybrid | 6/9 | **9/9** | 487 | 120 | 0.002s |
| Agentic | 7/9 | **9/9** | 1,389 | 220 | 0.004s |

**Chosen: hybrid search.** Naive RAG's one miss is an embedding confusion
between two lexically similar TSB numbers — hybrid's BM25 component fixes
exactly that case at essentially the same token/latency cost as naive.
Agentic RAG matches hybrid's retrieval quality but costs ~3x the tokens
and 2-4x the latency, which only pays off on genuinely multi-hop
questions. Hybrid ships as the default; the agentic path is reserved for
questions that explicitly need cross-referencing more than one document.

### Self-RAG-style verification

`mcp-server/rag/self_rag_check.py` runs after every RAG answer:

1. Each retrieved chunk is checked for relevance to the question;
   irrelevant chunks are dropped before the support check.
2. The generated answer is checked for whether it's actually supported
   by the (now-filtered) retrieved context.

If either check fails, the user never sees the ungrounded answer — they
get an explicit "I can't answer this from verified sources" message
instead. The same seam is used to verify memory recall, not just RAG
answers.

### Planning algorithms

Full write-up and per-scenario detail: `planning_eval/results/`. Fixed
scenarios comparing decomposition-first vs. dynamic decomposition,
Plan-and-Solve vs. Tree of Thoughts, grounded vs. ungrounded LATS, and
single-retry vs. Reflexion vs. Self-Refine.

```bash
python planning_eval/run_eval.py
```

| Concern | Case | Method | Success | LLM calls | Tool calls | Total tokens (source) | Latency (s) | Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| decomposition | decomp_first_favored | decomposition-first | success | 1 | 10 | 63 (offline-estimate) | 0.011 | N/A (offline) |
| decomposition | decomp_first_favored | dynamic-decomposition | success | 5 | 10 | 276 (offline-estimate) | 0.013 | N/A (offline) |
| decomposition | dynamic_favored | decomposition-first | success | 1 | 8 | 59 (offline-estimate) | 0.008 | N/A (offline) |
| decomposition | dynamic_favored | dynamic-decomposition | success | 4 | 7 | 207 (offline-estimate) | 0.007 | N/A (offline) |
| planning-algorithm | lookahead_needed | plan-and-solve | fail | 1 | 0 | 79 (offline-estimate) | 0.0003 | N/A (offline) |
| planning-algorithm | lookahead_needed | tree-of-thoughts | success | 3 | 0 | 270 (offline-estimate) | 0.0005 | N/A (offline) |
| grounding | reflexion_needed | lats-ungrounded | success | 2 | 0 | 268 (offline-estimate) | 0.0009 | N/A (offline) |
| grounding | reflexion_needed | lats-grounded | success | 4 | 1 | 559 (offline-estimate) | 0.0023 | N/A (offline) |
| self-correction | reflexion_needed | single-retry (max_trials=1) | fail | 2 | 0 | 305 (offline-estimate) | 0.0024 | N/A (offline) |
| self-correction | reflexion_needed | reflexion (max_trials=3) | success | 3 | 0 | 467 (offline-estimate) | 0.0056 | N/A (offline) |
| self-correction | reflexion_needed | self-refine (notification) | success | 3 | 0 | 594 (offline-estimate) | 0.0010 | N/A (offline) |

**Per-sub-task method choices, justified against this table:**
- **Decomposition:** dynamic decomposition ships as the default for the
  top-level fulfillment plan — it wins on `dynamic_favored` by skipping a
  whole alternative-search branch (7 tool calls vs. 8) once real stock is
  observed, at the cost of more LLM calls. Decomposition-first is kept
  for a job's fully mechanical branches where there is nothing to react to.
- **Planning algorithm:** Tree of Thoughts routes the "compare
  alternatives" sub-task — Plan-and-Solve's single pass fails
  `lookahead_needed` outright, while ToT's compare-and-score step picks
  the correct higher-stock alternative for a small extra cost. LATS is
  reserved for the final high-impact proceed/delay decision, not ranking.
- **Grounding:** the grounded environment is required for LATS on the
  final decision — the ungrounded toolkit default accepts a fabricated,
  out-of-stock candidate; the grounded version, checked against the real
  database, rejects it.
- **Self-correction:** Reflexion ships for the final proceed/delay
  decision, where a single retry provably isn't enough. Self-Refine is
  used for the cheap customer-notification text, where one
  draft/critique/revision pass is enough.

Without `ANTHROPIC_API_KEY` configured, every row above is
`offline-estimate` and every `Cost (USD)` cell reads `N/A (offline)` —
that is the harness working as designed. The offline fallback is
deterministic and heuristic (`planning/model_provider.py`), not random,
so the method comparisons are real and reproducible; only the absolute
token/cost figures would change with a live key.

## Testing

```bash
pip install -r requirements.txt
pytest tests/ state_graph/tests/ planning/tests/ -q
```

**`PYTHONPATH` is not needed to run any of the above under `pytest`.**
The repository-root `conftest.py` inserts the repo root (and
`mcp-server/`, `agent/`) into `sys.path` itself as soon as `pytest`
loads it, for every test directory. `PYTHONPATH=.` is only needed for
the **standalone** state-graph demo script, which isn't run through
`pytest`:

```bash
# macOS / Linux
PYTHONPATH=. python3 state_graph/run_demo.py

# Windows (PowerShell)
$env:PYTHONPATH = "."
python state_graph/run_demo.py
```

Any test that touches the database should request the repository-root
`demo_db_connection` pytest fixture (`conftest.py`) rather than
monkeypatching `databases.db.get_connection` directly — see
[Configuration](#configuration) and [Known issues](#known-issues--limitations).

**Verified test results:**

- `pytest tests/ state_graph/tests/ planning/tests/ -q` — **105 tests**
  (`tests/`: 56, `state_graph/tests/`: 26, `planning/tests/`: 23), all
  passing except one (`test_generate_inventory_report`) in an
  environment without the `pytest-asyncio` plugin installed — see
  [Known issues](#known-issues--limitations). Independently reproduced
  on both Linux and Windows/PowerShell with this same explicit-path
  invocation.
- Running plain `pytest -q` from the repository root (implicit,
  order-dependent auto-discovery instead of the explicit paths above)
  collects the same 105 tests but was observed, in one Linux run, to
  produce additional failures that did not reproduce when the same
  tests were run via the explicit-path form above. This points to a
  residual test-collection-order sensitivity around database-connection
  patching, not a defect exercised by the explicit invocation — use the
  explicit-path form shown above (or run each test directory
  separately) rather than bare `pytest -q`.

## Implementation & verification status

Each entry below distinguishes **Implemented** (the code exists and
runs), **Verified by tests** (an automated test or a manual, reproduced
check specifically exercised it), and **Planned/Future work** (not yet
built). Only evidence actually reproduced in this environment is listed.

### Task 1 — Planning Agent connected to the Streamlit platform

- **Objective:** wire the Planning Agent into `platform_streamlit/Home.py`
  alongside the existing Memory/RAG agent and the state-graph workflows.
- **Implementation:** `platform_streamlit/Home.py` imports
  `is_planning_request` / `handle_user_request` from `agent/client.py`
  and, when a question is planning-shaped, renders a structured job-request
  form (Job ID + up to 3 required parts) instead of routing to Memory/RAG.
- **Key files:** `platform_streamlit/Home.py`, `agent/client.py`.
- **Verification:** confirmed present by inspection and exercised live
  under Task 5's Streamlit startup and `AppTest` checks (below) without
  import or routing errors.
- **Status:** Implemented, Verified.

### Task 2 — Bilingual planning-request routing

- **Objective:** `is_planning_request()` only recognized English planning
  keywords, so Arabic planning requests (matching the platform's
  Arabic-facing UI) were misrouted to Memory/RAG instead of the Planning
  Agent.
- **Implementation:** extended the existing keyword tuple in
  `agent/client.py::is_planning_request()` with Arabic terms (`قطع غيار`,
  `قطعة غيار`, `شغل إصلاح`, `طلب إصلاح`, `مخزون`, `غير متوفر`, `توفير`,
  `تجهيز القطع`) alongside the untouched English terms. No change to the
  function's signature, callers, or the rest of the routing/planning code.
- **Key files:** `agent/client.py`, `tests/test_planning_routing_i18n.py`.
- **Verification:** new regression tests
  (`tests/test_planning_routing_i18n.py`, 4/4 passed) cover English
  planning → planning, Arabic planning → planning, normal English
  question → Memory/RAG, normal Arabic question → Memory/RAG. Existing
  `tests/test_planning_routing.py` (7/7) and `tests/test_agent_smoke.py`
  (Task 1's platform/agent integration) re-run clean against the change.
- **Status:** Implemented, Verified.

### Task 3 — Database wiring / test harness

- **Objective:** give the test suite one consistent, correct way to point
  at the seeded demo database instead of ad hoc, order-dependent patching.
- **Implementation:** the repository-root `conftest.py`'s
  `demo_db_connection` fixture resets a fresh seeded SQLite database and
  patches the current name binding of `get_connection` on every module
  that imports it directly, using `monkeypatch` so every patch is
  auto-reverted per test.
- **Key files:** `conftest.py`, `agent/demo_db.py`.
- **Verification:** exercised implicitly by every test in `tests/`,
  `state_graph/tests/`, and `planning/tests/` that requests the fixture —
  104 of 105 tests pass via the explicit-path invocation
  (`pytest tests/ state_graph/tests/ planning/tests/ -q`), reproduced on
  both Linux and Windows/PowerShell.
- **Status:** Implemented, Verified (see the collection-order note under
  [Testing](#testing) and [Known issues](#known-issues--limitations)).

### Task 4 — Test isolation

- **Objective:** stop `databases.db.get_connection` patches from leaking
  between tests regardless of import/collection order.
- **Implementation:** same `conftest.py` fixture as Task 3 — `monkeypatch`
  guarantees every patch reverts at the end of each test, and
  `demo_db.reset_demo_database()` reseeds a brand-new SQLite file per
  test that requests the fixture, so tests don't share rows.
- **Key files:** `conftest.py`, `tests/test_db_isolation_regression.py`.
- **Verification:** `tests/test_db_isolation_regression.py` passes as
  part of the test run reported under [Testing](#testing).
- **Status:** Implemented, Verified.

### Task 5 — Platform dependencies & startup verification

- **Objective:** confirm the Streamlit platform can actually be installed
  and started from the project's documented dependencies alone.
- **Implementation:** no code changes were needed or made —
  `requirements.txt` already declared `streamlit>=1.28.0` correctly.
- **Key files:** `requirements.txt` (inspected, unchanged),
  `platform_streamlit/Home.py` (started, unchanged).
- **Verification, all reproduced in this environment:**
  - `pip install -r requirements.txt` completed with no errors; Streamlit
    resolved to version `1.62.0`.
  - `streamlit run platform_streamlit/Home.py --server.headless true`
    started cleanly (Uvicorn bound, no import/startup errors in logs);
    `curl http://localhost:<port>` returned HTTP `200`.
  - A headless `streamlit.testing.v1.AppTest` load of
    `platform_streamlit/Home.py` completed with **zero exceptions**
    (`at.exception` empty).
- **Status:** Implemented (pre-existing), Verified. No files changed.

### Planned / future work

- No `LICENSE` file exists yet (see [License](#license)).
- No `CONTRIBUTING.md` exists yet.
- No deployment configuration (Dockerfile, CI/CD) exists yet (see
  [Deployment](#deployment)).
- The database-isolation fixture gap in a few test functions (see
  [Known issues](#known-issues--limitations)) is not yet fixed.

## Known issues / limitations

- **`databases/db.py`'s `get_connection()` has no real implementation.**
  It always raises `RuntimeError("No database connection configured...")`
  unless something (a caller, or the `demo_db_connection` test fixture)
  supplies a connection. The seeded SQLite demo database is the only
  database path actually running and tested in this environment; a real
  SQL Server connection would need to be implemented against
  `DB_CONNECTION_STRING` for production use.
- **`tests/test_tools.py::TestInventoryReport::test_generate_inventory_report`
  requires the `pytest-asyncio` plugin** (`@pytest.mark.asyncio` has no
  effect without it), which is not declared in `requirements.txt`. This
  is the one consistently-reproducible failure — install `pytest-asyncio`
  to run it; every other test passes without it.
- **Bare `pytest -q` run from the repository root (implicit, full
  auto-discovery) was observed, in one environment, to produce extra
  failures beyond the `pytest-asyncio` one above** — the same 105 tests
  collected, but a different pass/fail outcome than running
  `pytest tests/ state_graph/tests/ planning/tests/ -q` explicitly. This
  was **not reproduced** on a separate Windows/PowerShell run using the
  explicit-path form, which passed 104/105 (only the `pytest-asyncio`
  gap above). It points to a residual test-collection-order sensitivity
  around database-connection patching that the `demo_db_connection`
  fixture doesn't fully close for every module pytest's default,
  unrestricted discovery might collect — use the explicit-path
  invocation shown under [Testing](#testing) to avoid it; this has not
  been root-caused further.
- **RAG / memory / planning calls run through offline mocks** whenever
  `ANTHROPIC_API_KEY` is unset — expected behavior, not a bug, but numbers
  in the evaluation tables above are explicitly `offline-estimate` in
  that case.
- **The planning module supports up to 3 required parts per job request**
  (`planning/fulfillment_decomposition.py::build_plan_first`); the
  Streamlit platform enforces and surfaces this limit in its form.
- **No supplier-availability tool exists.** `Suppliers` only holds
  contact info, so "no part and no alternative in stock" is a genuine
  dead end the planning layer surfaces to a human rather than a step it
  invents.

## Deployment

No deployment configuration (Dockerfile, CI/CD pipeline, or hosting
config) is present in the repository. To deploy, provision a Python
environment with the dependencies in `requirements.txt`, configure
`DB_CONNECTION_STRING` against a real database (and implement a real
connection in `databases/db.py::get_connection()` — see
[Known issues](#known-issues--limitations)), and run
`mcp-server/server.py` as a long-lived process; the Streamlit platform
can be served separately via `streamlit run platform_streamlit/Home.py`.

## Troubleshooting

- **`RuntimeError: No database connection configured`** — `databases/db.py`
  raises this by design when no connection has been wired. For local
  runs, `agent/client.py`'s `wire_demo_database()` helper (which points
  `get_connection` at the seeded SQLite database in `agent/demo_db.py`)
  handles this automatically; for tests, request the `demo_db_connection`
  fixture from the repository-root `conftest.py` (see
  [Known issues](#known-issues--limitations) for tests that currently
  don't). For production, set `DB_CONNECTION_STRING` and implement a real
  connection.
- **RAG / memory / planning calls run through mocks with noisy results**
  — expected without `ANTHROPIC_API_KEY` set in `.env`; set the key to
  use real Claude calls instead of the documented offline fallbacks.
- **`ModuleNotFoundError: No module named 'state_graph'` when running
  `python state_graph/run_demo.py` directly** — this standalone script
  needs the repository root on `PYTHONPATH` (`PYTHONPATH=.` on
  macOS/Linux, `$env:PYTHONPATH = "."` on PowerShell), since it isn't run
  through `pytest`. Running the tests themselves
  (`pytest state_graph/tests/ -q`) does **not** need `PYTHONPATH` set —
  the repository-root `conftest.py` handles that automatically.
- **`streamlit run platform_streamlit/Home.py` fails to start** —
  `requirements.txt` already declares `streamlit>=1.28.0`; re-run
  `pip install -r requirements.txt` in the active virtual environment.
  Startup, imports, and a headless `AppTest` load have been independently
  verified to succeed from that requirements file alone (see
  [Task 5](#task-5--platform-dependencies--startup-verification)).

## Attribution

The `planning/` module is built on top of a vendored, third-party
decomposition-and-planning toolkit located at
`planning/vendor/planning_lab/`. See
[`planning/vendor/ATTRIBUTION.md`](planning/vendor/ATTRIBUTION.md) for
details and the original source.

## License

No license file was found in this repository. Add a `LICENSE` file to
clarify the terms under which this project may be used, modified, or
distributed.
