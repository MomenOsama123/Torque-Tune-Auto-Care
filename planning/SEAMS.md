# Seams -- current Week 4 status

## 1. Model provider -- RESOLVED (Issue 2)
Confirmed by inspecting planning/vendor/planning_lab/algorithms/*.py: every
algorithm takes `llm: BaseChatModel` and only ever calls
`llm.invoke(messages, **kwargs)` or
`llm.with_structured_output(Schema, method="json_schema").invoke(...)`.
That's LangChain's public interface, not toolkit-specific.

Decision: `planning/model_provider.py` uses `langchain_anthropic.ChatAnthropic`
(confirmed to support `with_structured_output(..., method="json_schema")`
natively, requires langchain-anthropic>=1.1.0) when `ANTHROPIC_API_KEY` is
set, else a deterministic offline double implementing the same two methods
-- same real-or-mock pattern as `mcp-server/rag/llm_client.py`. Zero changes
needed inside `planning/vendor/planning_lab/algorithms/*.py`.

Rejected alternative: reshaping `mcp-server/rag/llm_client.py`'s raw-text
`llm_call()` into a fake `BaseChatModel`. Its (text, in_tok, out_tok)
contract has no structured-output concept at all -- faking
`with_structured_output()` on top of it convincingly would mean
re-implementing a meaningful slice of LangChain, a bigger rebuild than
adding one official dependency for the same provider.

## 2. environment.py (toolkit default: randomized beta-distribution score)
RESOLVED -- `planning/grounded_environment.py` is the project-owned
environment adapter. It validates planning decisions against the real
spare-parts database through the existing MCP read tools. The vendored
randomized `Environment` remains untouched and is used only for the
explicit ungrounded-vs-grounded evaluation comparison.

## 3. Execution/tool-calling layer -- RESOLVED (Issue 2)
The vendored `decomposition.execute_plan()` / `dynamic_decomposition
.dynamic_decomposition()` always call `llm.invoke()` per node -- free
prose, no tool-calling interface of their own. `planning/
fulfillment_decomposition.py` does NOT call those two functions; it reuses
only `planning_lab.models.Plan`/`Task` (decomposition-first) and the
`DynamicDecision` schema + loop shape (dynamic), and writes its own
executor that dispatches each node to a real call into
`mcp-server/tools/read_tools.py` (`search_spare_part`, `check_stock`,
`suggest_alternative`), with the LLM used only for the final synthesis
node. See the module docstring in `fulfillment_decomposition.py` for the
exact real dependency chain this encodes.

## 4. artifacts/ trace format
Still open -- planning_eval/ (Issue 7) should read the vendored trace
format rather than building a second logging system. Not touched in
Issue 2; `fulfillment_decomposition.Telemetry` (tool_calls, llm_calls,
tool_call_log) is real call accounting for Issue 7 to consume, not a
replacement for the artifact format.

## 5. New: Plan.tasks max_length=8 (planning_lab/models.py)
Discovered while implementing Issue 2, not previously listed. Caps
`build_plan_first()` at 3 required parts per job (2 tasks/part + 1
synthesis = 7 <= 8). Documented in `fulfillment_decomposition.py`'s module
docstring; a >3-part job raises `pydantic.ValidationError`, not a silent
truncation. Splitting a larger job across multiple plans is unaddressed --
flagged for whoever picks up Issue 6 (integration) or Issue 7 (eval suite),
since a realistic job could plausibly need more than 3 parts.

## 6. Planning algorithms + routing -- RESOLVED (Issue 3)
`planning/routing.py` maps sub-task characteristics to Plan-and-Solve /
Tree of Thoughts / LATS (all three vendored unmodified from
`algorithms/{plan_and_solve,tree_of_thoughts,lats}.py`), and
`planning/fulfillment_planning.py` wires that routing into the real
workflow: `notify` -> Plan-and-Solve, `choose_alt` (2+ stocked
alternatives) -> ToT, `decide` -> LATS. LATS still uses the vendored
toolkit's default (ungrounded, randomized) `Environment` -- unchanged on
purpose, since replacing it is Issue 4's job, not Issue 3's.
`planning/model_provider.py` gained offline mocks for `ThoughtCandidates`,
`ThoughtEvaluation`, `LATSActionBatch`, `ValueEstimate` (Issue 2's
`DynamicDecision` mock untouched).

## 7. Live agent integration -- RESOLVED
`agent/client.py` now exposes `handle_user_request()`, the live routing seam
used by the CLI agent. Repair/spare-parts requests are routed into the Week 4
planning workflow; ordinary requests retain the existing Memory/RAG path.
The planning result is written into the same session memory, so planning runs
alongside (not instead of) the existing Memory/RAG capabilities. The live
route calls `build_plan_first()` / `execute_plan_first()` and then
`run_planning_layer()`, which dispatches Plan-and-Solve / Tree of Thoughts /
LATS and the grounded environment.
