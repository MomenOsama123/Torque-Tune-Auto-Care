# planning/vendor/planning_lab -- vendored from the reference toolkit

Source: https://github.com/AmrSheta22/task_decomposition_and_planning
Vendored: full `planning_lab/` package, copied in unmodified (Issue 2).

## Files, verbatim, unmodified
- `planning_lab/models.py` -- Task/Plan/Thought/EnvironmentFeedback
  Pydantic models, DAG validation (`Plan.validate_dag`, cycle check via
  `networkx.is_directed_acyclic_graph`), `execution_batches()`
  (topological generations). **Reused directly** by
  `planning/fulfillment_decomposition.py` -- not reimplemented.
- `planning_lab/algorithms/decomposition.py`,
  `dynamic_decomposition.py`, `plan_and_solve.py`, `tree_of_thoughts.py`,
  `self_refine.py`, `reflexion.py`, `lats.py`, `environment.py` --
  vendored as a set because `algorithms/__init__.py` imports all of them
  together. Only `dynamic_decomposition.DynamicDecision` (the schema) is
  used as of Issue 2. The others are not called yet -- see the Week 4
  section of the main README for which Issue wires each one in
  (PS/ToT/LATS -> Issue 3, self_refine/reflexion -> Issue 5,
  environment -> Issue 4).
- `planning_lab/cli.py` -- vendored for reference/attribution only, NOT
  used by this project. It hardcodes `ChatMistralAI` + argparse for the
  toolkit's own generic demo goals. Our real entry point is
  `planning/fulfillment_decomposition.py`, using
  `planning/model_provider.py` for the model swap (see SEAMS.md item 1).

## Not modified
Nothing in this directory was hand-edited. Where toolkit behaviour needed
adapting (model provider, real-tool execution instead of LLM prose per
node), the adaptation lives in `planning/` alongside this directory, not
inside it -- so a diff against upstream stays clean.
