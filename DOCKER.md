# Running Torque Tune Auto Care in Docker

## Container architecture — why it's one image, two services, not three+ containers

`mcp-server/fastmcp.py`'s `FastMCP.run()` is currently a no-op, and every
caller (`state_graph/`, `agent/client.py`, `platform_streamlit/Home.py`)
imports the server's tools **in-process** — plain Python function calls,
not a network call over stdio or HTTP. There is no real network boundary
in the code to split a container on yet, so splitting into an
"mcp-server container" + "agent container" + "platform container" would
be fake architecture that doesn't match what the code actually does.

Instead, there's **one image** (`torque-tune:latest`, built once from
the single `Dockerfile`) and **two services** in `docker-compose.yml`
that both run that same image with different startup commands:

```
+------------------------------------------+
|      torque-tune:latest (one image)       |
+---------------------+----------------------+
|   platform service   |    test service      |
|  (always running,    |  (one-shot, only     |
|   restart: unless-   |   runs with          |
|   stopped)            |   --profile test)    |
|                       |                       |
|  runs, in-process:    |  runs:                |
|   - Streamlit UI      |   - pytest -q         |
|   - state_graph/      |                       |
|   - mcp-server/*      |                       |
|     (imported, not    |                       |
|      called over a    |                       |
|      network)         |                       |
+---------------------+----------------------+
              |
    shared named volumes:
    state_graph_data, mcp_server_data, rag_kb_data
```

If `mcp-server/` ever gets a real transport (an HTTP server via
FastAPI/uvicorn, for example), splitting it into its own long-running
service container becomes meaningful. Not before — a container that
imports the same Python module in-process gives you nothing a second
container wouldn't just duplicate.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Single reproducible image, non-root user, healthcheck |
| `docker-entrypoint.sh` | Picks which of the project's existing entry points to run |
| `docker-compose.yml` | The `platform` service (Streamlit, always on) + the `test` service (one-shot) + volumes |
| `.dockerignore` | Keeps secrets and host-specific junk out of the build context |
| `requirements-lock.txt` | Pinned versions (see below for why) |

## First-time setup

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY if you have one; optional
docker compose build --no-cache
docker compose up -d
# open http://localhost:8501
```

## Commands you'll actually use day to day

| What you want | Command |
|---|---|
| Build (or rebuild after code changes) | `docker compose build --no-cache` |
| Start the platform in the background | `docker compose up -d` |
| Check it's actually running / healthy | `docker compose ps` (look for `Up ... (healthy)`) |
| Watch logs live | `docker compose logs -f platform` |
| Restart (simulates a crash-recover cycle) | `docker compose restart platform` |
| Stop everything | `docker compose down` |
| Run a one-off command inside the running container | `docker compose exec platform sh -c "<command>"` |
| Run the full pytest suite as a one-shot job | `docker compose --profile test run --rm test` |
| Run the state-graph demo inside the container | `docker compose exec platform sh -c "PYTHONPATH=. python3 state_graph/run_demo.py"` |
| Get a shell inside the container for debugging | `docker compose exec platform sh` |

**Every code change requires a rebuild.** The image is a snapshot of the
source taken at `docker compose build` time — it does not track live
edits. If a teammate pushes a fix (e.g. to `tool_registry` enforcement
or the failing tests), pull it and rebuild before it shows up in the
running container:

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

Data in the named volumes (checkpoints, tickets, tool registry, RAG
docs) is untouched by a rebuild — only the code changes.

## Modes the entrypoint supports

`docker-entrypoint.sh` picks one of these based on the first argument —
useful with `docker compose run --rm platform <mode>` for anything that
isn't the always-on platform service:

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

```bash
docker compose run --rm platform state-graph-demo
docker compose --profile test run --rm test
```

## Volumes — why they exist, not just "good practice"

Three things this project writes to disk **must** survive a container
being recreated, or the "durable" and "resumable" claims in the
Final-Project brief stop being true the moment the container restarts:

1. `state_graph/_data/state_graph.sqlite3` — the Checkpoints + Tickets
   tables (`state_graph/db.py`, fixed path by design — see its module
   docstring on why the path isn't a tempfile). Without a volume, every
   container recreate wipes every paused/failed thread.
2. `mcp-server/_data/tool_registry.json` — per-agent tool visibility set
   from the admin panel (`mcp-server/tool_registry.py`).
3. `mcp-server/resources/knowledge_base/*.md` — RAG documents added or
   removed from the admin panel (`mcp-server/rag/registry.py`).

### Proof, verified end to end inside a real container

```bash
docker compose up -d
docker compose exec platform sh -c "PYTHONPATH=. python3 state_graph/run_demo.py"
# -> ends with a real filed Failure Ticket, e.g. "status=failed ticket_id=10"

docker compose restart platform
docker compose ps   # wait for "Up ... (healthy)"

docker compose exec platform sh -c \
  "PYTHONPATH=. python3 -c \"from state_graph.tickets import list_tickets; print('open tickets after restart:', len(list_tickets()))\""
# -> open tickets after restart: 1
```

The ticket count is unchanged after the restart — proof the named
volume, not the container's writable layer, is what's holding the
state. This exact command sequence was run and verified for this
project. A fresh container recreate (`docker compose down && docker
compose up -d`) proves the same thing even more strongly, since `down`
removes the container entirely and only the volume survives.

## Why `requirements-lock.txt` and not `requirements.txt` in the build

`requirements.txt` pins with `>=`, which is right for a human installing
locally (get security fixes), but wrong for a **reproducible** image —
two builds a month apart can silently pull different transitive
versions. `requirements-lock.txt` pins exact versions verified against
this codebase (`state_graph/tests/` — 26/26 — and `state_graph/run_demo.py`
both pass on these pins, and `docker compose build` was verified to
complete cleanly with them).

**Known pin conflict, already fixed**: `pytest==9.1.1` together with
`pytest-asyncio==0.24.0` fails to resolve —
`pytest-asyncio 0.24.0 depends on pytest<9,>=8.2`. The lock file here
uses `pytest-asyncio==1.4.0`, which supports `pytest 9.x`. If you
regenerate the lock file yourself and pin an older `pytest-asyncio`
again, you'll hit the same `ResolutionImpossible` error — check the
version you're pinning supports whatever `pytest` version is pinned
alongside it.

Regenerate the lock file deliberately when you want to move to newer
versions:

```bash
pip install -r requirements.txt pytest-asyncio --break-system-packages
pip freeze --local > requirements-lock.txt   # then trim to direct deps
```

`pytest-asyncio` is added here because `tests/test_tools.py` has an
`@pytest.mark.asyncio` test that isn't runnable without it — it's not in
the original `requirements.txt`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop isn't running | Start Docker Desktop, wait for the whale icon to stop animating, then `docker info` to confirm |
| `pip install ... exit code 1` with no other detail | Log got truncated/collapsed | Rerun with `docker compose build --progress=plain --no-cache` to see the full, uncollapsed pip output |
| `ResolutionImpossible ... pytest-asyncio depends on pytest<9` | Incompatible pinned versions in `requirements-lock.txt` | Already fixed in the lock file shipped here (`pytest-asyncio==1.4.0`) — see above if you regenerate it yourself |
| scikit-learn/numpy build fails from source | Missing Fortran/BLAS toolchain, or pip too old to find a prebuilt wheel | The `Dockerfile` already installs `gfortran` + `libopenblas-dev` and upgrades `pip`/`setuptools`/`wheel` before installing dependencies |
| Container stuck on `Restarting` for a long time | Something crashing on startup | `docker compose logs --tail=50 platform` |
| Volume data missing tools/RAG docs after a rebuild you didn't expect | Named volumes are separate from the image — `docker compose build` never touches them, but `docker volume rm` or `docker compose down -v` does | Never run `-v` unless you actually want to wipe the demo data |

## What Docker does *not* fix by itself

Packaging this in Docker does not close the gap flagged in the platform
review: `mcp-server/tool_registry.py` is only consulted by the
`memory_rag` chat path in `platform_streamlit/Home.py`, not by
`mcp-server/server.py`'s tool dispatch or by the three state graphs.
Containerizing the app ships that gap unchanged — fix the enforcement in
the application code; Docker only guarantees the *environment* is
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

`build-essential`, `gfortran`, and `libopenblas-dev` are installed in
the image so `numpy`/`scikit-learn` build cleanly even on architectures
where PyPI doesn't ship a prebuilt wheel (e.g. some ARM hosts) — this is
what actually makes the build reproducible across a mixed team (Apple
Silicon + Intel + Windows + CI runners), not just pinned versions alone.
