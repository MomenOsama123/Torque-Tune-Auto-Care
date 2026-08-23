#!/usr/bin/env sh
# docker-entrypoint.sh
#
# One image, several modes -- mirrors the "Available Scripts / Commands"
# table in README.md exactly, so `docker run <image> <mode>` behaves the
# same way running the command locally with PYTHONPATH=. would.
set -e

mode="${1:-platform}"
shift || true

case "$mode" in
  platform)
    exec streamlit run platform_streamlit/Home.py \
      --server.address=0.0.0.0 \
      --server.port=8501 \
      --server.headless=true \
      "$@"
    ;;
  state-graph-demo)
    exec python3 state_graph/run_demo.py "$@"
    ;;
  state-graph-tests)
    exec python3 -m pytest state_graph/tests/ -q "$@"
    ;;
  test)
    exec python3 -m pytest -q "$@"
    ;;
  agent)
    exec python3 agent/client.py "$@"
    ;;
  planning-demo)
    exec python3 planning/fulfillment_demo.py "$@"
    ;;
  mcp-server)
    exec python3 mcp-server/server.py "$@"
    ;;
  shell)
    exec /bin/sh
    ;;
  *)
    echo "Unknown mode: $mode" >&2
    echo "Valid modes: platform | state-graph-demo | state-graph-tests | test | agent | planning-demo | mcp-server | shell" >&2
    exit 1
    ;;
esac
