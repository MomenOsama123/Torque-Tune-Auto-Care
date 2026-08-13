"""Torque Tune Week 4 decomposition/planning extension.

The planning layer is a live-agent capability, not a standalone demo:
``agent.client.handle_user_request()`` routes repair/spare-parts requests
into this package while the existing Memory/RAG path remains available for
other requests.

Main flow::

    agent.client
        -> JobRequest
        -> build_plan_first / execute_plan_first
        -> run_planning_layer
        -> Plan-and-Solve / Tree of Thoughts / LATS
        -> GroundedFulfillmentEnvironment
        -> existing MCP tools + database

The vendored planning toolkit under ``planning/vendor/planning_lab`` remains
unchanged and is reused as the implementation layer for the planning
algorithms and plan/task models.
"""
