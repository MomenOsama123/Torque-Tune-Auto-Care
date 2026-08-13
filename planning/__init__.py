"""
planning/ -- Week 4 Decomposition & Planning extension.

STATUS: Issue 1 (setup) + Issue 2 (task decomposition) + Issue 3
(planning algorithms + routing) done. Self-correction, grounded
environment, integration, eval harness, and docs/demo (Issues 4-8) not
started.

Sits next to mcp-server/memory/ and mcp-server/rag/ (Week 3). Reuses the
same mcp-server/ and databases/. Does NOT import from or modify
agent/client.py (the Week 3 memory/RAG agent's code path).

planning/vendor/planning_lab/       -- the forked reference toolkit
    (github.com/AmrSheta22/task_decomposition_and_planning), vendored
    verbatim -- see vendor/ATTRIBUTION.md for exactly what's used vs.
    untouched.
planning/model_provider.py          -- the model-provider seam (Issue 1/2,
    see SEAMS.md item 1): real Claude via langchain_anthropic.ChatAnthropic,
    offline heuristic fallback otherwise.
planning/fulfillment_decomposition.py -- Issue 2: decomposition-first
    (build_plan_first/execute_plan_first) and dynamic decomposition
    (dynamic_fulfillment) for "prepare spare parts for a repair job when a
    required part is out of stock", adapted to real mcp-server/tools/
    read_tools.py calls against the actual database.
planning/routing.py                 -- Issue 3: the router. Maps a
    sub-task's real characteristics (mechanical / compare-alternatives /
    high-impact-decision) to Plan-and-Solve / Tree of Thoughts / LATS.
planning/fulfillment_planning.py    -- Issue 3: consumes Issue 2's
    decomposition output and runs it through the router (choose_alt ->
    ToT, decide -> LATS, notify -> Plan-and-Solve). Does not modify or
    re-run fulfillment_decomposition.py.
planning/fulfillment_demo.py        -- runnable demo of the two Issue 2
    methods diverging on a concrete scenario.
planning/tests/                     -- Issue 2 tests (cycle rejection, the
    8-task cap, the divergence scenario) + Issue 3 tests (routing choice,
    PS/ToT/LATS execution, Issue 2 output compatibility).
planning/SEAMS.md                   -- seam-by-seam status, updated as
    later Issues land.
"""
