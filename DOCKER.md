# Running Torque Tune Auto Care in Docker

## Why one image, not several containers

`mcp-server/fastmcp.py`'s `FastMCP.run()` is currently a no-op, and every
caller (`state_graph/`, `agent/client.py`, `platform_streamlit/Home.py`)
imports the server's tools **in-process** rather than talking to it over
a socket or stdio. There is no real network boundary to split on yet, so
`docker-compose.yml` here defines one image (`torque-tune:latest`) with
several **modes**, not separate "mcp-server" / "agent" / "platform"
services. If you later add a real transport (stdio or HTTP) to
`mcp-server/`, splitting `mcp-server` into its own long-running service
container becomes meaningful — not before.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Single reproducible image, non-root user, healthcheck |
| `docker-entrypoint.sh` | Picks which of the project's existing entry points to run |
| `docker-compose.yml` | The `platform` service (Streamlit) + volumes + an optional `test` profile |
| `.dockerignore` | Keeps secrets and host-specific junk out of the build context |
| `requirements-lock.txt` | Pinned versions (see below for why) |

## Quick start

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY if you have one; optional
docker compose build
docker compose up -d
# open http://localhost:8501
```

## Why `requirements-lock.txt` and not `requirements.txt` in the build

`requirements.txt` pins with `>=`, which is right for a human installing
locally (get security fixes), but wrong for a **reproducible** image —
two builds a month apart can silently pull different transitive
versions. `requirements-lock.txt` pins exact versions that were verified
against this codebase (`state_graph/tests/` — 26/26 — and
`state_graph/run_demo.py` both pass on these exact pins). Regenerate it
deliberately when you want to move to newer versions:

```bash
pip install -r requirements.txt pytest-asyncio --break-system-packages
pip freeze --local > requirements-lock.txt   # then trim to direct deps
```

`pytest-asyncio` is added here because `tests/test_tools.py` has an
`@pytest.mark.asyncio` test that isn't otherwise runnable — it's not in
the original `requirements.txt`.

## Modes (`docker run <image> <mode>`, or `docker compose run --rm platform <mode>`)

| Mode | Runs |
|---|---|
| `platform` (default) | `streamlit run platform_streamlit/Home.py` on `0.0.0.0:8501` |
| `state-graph-demo` | `state_graph/run_demo.py` — the narrated 5-scenario walkthrough |
| `state-graph-tests` | `pytest state_graph/tests/ -q` |
| `test` | the full `pytest -q` suite |
| `agent` | `agent/client.py` — the CLI MCP client demo |
| `planning-demo` | `planning/fulfillment_demo.py` |
| `mcp-server` | `mcp-server/server.py` standalone |
| `shell` | drops into `/bin/sh` for debugging |

Example:

```bash
docker compose run --rm platform state-graph-demo
docker compose --profile test run --rm test
```

## Volumes — why they exist, not just "good practice"

Three things this project writes to disk **must** survive a container
being recreated, or the "durable" and "resumable" claims in the
Final-Project brief stop being true the moment you run
`docker compose up` a second time:

1. `state_graph/_data/state_graph.sqlite3` — the Checkpoints + Tickets
   tables (`state_graph/db.py`, fixed path by design — see its module
   docstring on why the path isn't a tempfile). Without a volume, every
   `docker compose down` wipes every paused/failed thread.
2. `mcp-server/_data/tool_registry.json` — per-agent tool visibility set
   from the admin panel (`mcp-server/tool_registry.py`).
3. `mcp-server/resources/knowledge_base/*.md` — RAG documents added or
   removed from the admin panel (`mcp-server/rag/registry.py`).

**Proof this actually matters** (run outside Docker, but it's exactly
what a container recreate does — a brand-new Python process reading the
same file path):

```bash
rm -f state_graph/_data/state_graph.sqlite3
PYTHONPATH=. python3 -c "
from state_graph.bootstrap import ensure_wired
import agent.demo_db as demo_db; demo_db.reset_demo_database()
import databases.db as db; db.get_connection = demo_db.build_demo_connection
from state_graph.graphs.purchase_order_graph import decompose_into_supplier_batches
from state_graph.checkpointer import Checkpointer
state = {'thread_id': 'proof', 'user_id': 2}
state.update(decompose_into_supplier_batches(state))
Checkpointer().save(thread_id='proof', graph_name='purchase_order',
    node_name='decompose_into_supplier_batches', status='running', state=state)
"
# fresh interpreter, same file:
PYTHONPATH=. python3 -c "
from state_graph.checkpointer import Checkpointer
cp = Checkpointer().latest('proof')
print(cp.node_name, cp.status)
"
# -> decompose_into_supplier_batches running
```

Verify it inside Docker itself:

```bash
docker compose up -d
docker compose exec platform sh -c \
  "PYTHONPATH=. python3 state_graph/run_demo.py" | grep ticket_id
docker compose restart platform
docker compose exec platform sh -c \
  "PYTHONPATH=. python3 -c \"from state_graph.tickets import list_tickets; print(len(list_tickets()))\""
# ticket count should be unchanged after the restart -- proves the
# volume, not the container's writable layer, is what's holding state.
```

## What Docker does *not* fix by itself

Packaging this in Docker does not close the gap already flagged in the
platform review: `mcp-server/tool_registry.py` is only consulted by the
`memory_rag` chat path in `platform_streamlit/Home.py`, not by
`mcp-server/server.py`'s tool dispatch or by the three state graphs.
Containerizing the app ships that gap unchanged — fix the enforcement in
the app code first; Docker only guarantees the *environment* is
reproducible, not that the admin toggle actually restricts tool access.

## `agent/demo_db.py` is intentionally ephemeral

The seeded business-data demo database (`SpareParts`, `Users`,
`InventoryLogs`, ...) lives in a `tempfile.mkstemp()` file inside the
container, on purpose (see that module's docstring) — it's meant to
reset to a clean seed on every fresh run, unlike the checkpoint/ticket
DB above. Don't add a volume for it unless you specifically want demo
data to persist across restarts; if you do, point
`agent.demo_db._DB_PATH` at a fixed path under a mounted volume instead
of relying on `tempfile`.

## Multi-arch / CI note

`build-essential` is installed in the image so `numpy`/`scikit-learn`
build cleanly even on architectures where PyPI doesn't ship a prebuilt
wheel (e.g. some ARM hosts) — this is what actually makes the build
reproducible across a mixed team (Apple Silicon + Intel + CI runners),
not just pinned versions alone.
