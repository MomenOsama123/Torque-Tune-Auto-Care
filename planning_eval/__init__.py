"""planning_eval/ -- Issue 7's fixed test suite and evaluation harness.

Runs every required comparison (decomposition-first vs dynamic,
Plan-and-Solve vs Tree of Thoughts vs LATS, ungrounded vs grounded LATS,
single-retry vs Reflexion, Self-Refine) against a fixed set of real
spare-parts fulfillment scenarios, and writes the resulting comparison
table + per-run JSON traces to planning_eval/results/.

Entry point: `python planning_eval/run_eval.py`
"""
