# syntax=docker/dockerfile:1

# Torque Tune Auto Care -- reproducible container image.
#
# The project has no real network boundary between "MCP server" and
# "agent" today -- mcp-server/fastmcp.py's FastMCP.run() is a no-op and
# every module (state_graph/, agent/, platform_streamlit/) imports the
# server's tools in-process (see mcp-server/tool_registry.py,
# platform_streamlit/Home.py). So this is ONE image with several possible
# entrypoint modes, not separate service images -- splitting it into real
# containers only makes sense once the server actually speaks a protocol
# (stdio/HTTP) over the wire.

FROM python:3.12-slim AS base

# Prevents .pyc clutter in the image layer and keeps stdout/stderr
# unbuffered so `docker logs` shows Streamlit/pytest output live.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# numpy / scikit-learn need a C toolchain to build from sdist on slim
# images for some platforms -- build-essential keeps the build
# reproducible across host architectures instead of depending on a
# prebuilt wheel always being available.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first so Docker's layer cache is
# reused on every rebuild that doesn't touch dependencies -- this is
# most of what makes rebuilds fast and reproducible.
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt

# Now copy the rest of the source.
COPY . .

# Non-root runtime user -- the app only ever writes inside /app/*/_data/
# (state_graph/_data/, mcp-server/_data/) and to a tempfile-backed demo
# DB, none of which need root.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/state_graph/_data /app/mcp-server/_data \
    && chown -R appuser:appuser /app
USER appuser

RUN chmod +x docker-entrypoint.sh

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
# Default mode -- override with `docker run <image> test|demo|mcp-server|agent|shell`
CMD ["platform"]
