"""
planning/model_provider.py

The model-provider seam for planning/vendor/planning_lab (Issue 1,
finished here now that the toolkit's actual interface is known -- see
planning/SEAMS.md, item 1).

The toolkit's algorithms depend only on langchain_core.BaseChatModel's
public contract:
    llm.invoke(messages, **kwargs) -> object with a .content: str
    llm.with_structured_output(PydanticModel, method="json_schema") \
        .invoke(messages, **kwargs) -> a validated PydanticModel instance

That's a real, stable, documented LangChain interface -- not something
specific to the toolkit's internals. langchain_anthropic.ChatAnthropic
implements with_structured_output(..., method="json_schema") natively
(confirmed; requires langchain-anthropic>=1.1.0). So swapping away from
ChatMistralAI needs zero changes inside
planning/vendor/planning_lab/algorithms/*.py -- only this file, matching
the lab's "keep the interfaces, don't rebuild the search loops" rule.

Decision (see SEAMS.md item 1): use langchain_anthropic.ChatAnthropic
rather than reshaping mcp-server/rag/llm_client.py's raw-text seam into a
fake BaseChatModel. llm_client.llm_call() returns (text, in_tok, out_tok)
with no structured-output contract at all -- faking with_structured_output()
convincingly on top of it would mean re-implementing a meaningful slice of
LangChain, a bigger and more fragile rebuild than adding one official,
well-supported dependency for the same provider (Anthropic) this repo
already calls directly via the `anthropic` package.

Offline fallback: this repo's convention (mcp-server/rag/llm_client.py)
is that everything still runs end to end without ANTHROPIC_API_KEY, via a
documented heuristic mock, never a random one. get_llm() follows the same
rule.
"""

from __future__ import annotations

import os
import re
from types import SimpleNamespace

MODEL = "claude-sonnet-4-6"


def get_llm():
    """Returns a BaseChatModel-compatible object: real Claude via
    langchain_anthropic when ANTHROPIC_API_KEY is set, otherwise the
    offline heuristic double below. Callers never branch on which one
    they got -- same pattern as mcp-server/rag/llm_client.llm_call()."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=MODEL, api_key=api_key, max_retries=2)
    return _OfflineFulfillmentLLM()


class _StructuredOfflineCall:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, messages, **kwargs):
        prompt = messages[-1][1]
        return _mock_structured(self.schema, prompt)


class _OfflineFulfillmentLLM:
    """Deterministic, heuristic stand-in -- same philosophy as
    mcp-server/rag/llm_client.py's mock: no randomness, reasoning is
    documented, real end-to-end runs without a key."""

    def invoke(self, messages, **kwargs):
        prompt = messages[-1][1]
        return SimpleNamespace(content=_mock_invoke(prompt))

    def with_structured_output(self, schema, *, method):
        assert method == "json_schema"
        return _StructuredOfflineCall(schema)


def _mock_synthesis(prompt: str) -> str:
    """Heuristic stand-in for the final proceed/alternative/delay
    recommendation. Reads the real findings text
    planning/fulfillment_decomposition.py put into the prompt
    (quantity=N, alternatives=[...]) -- not a random guess."""
    direct_hit = re.search(r"(\S[\S ]*): id=\d+ quantity=([1-9]\d*)", prompt)
    if direct_hit:
        return (
            f"mock heuristic: proceed with the originally requested part "
            f"(found positive stock -- {direct_hit.group(0)})."
        )
    alt_hit = re.search(r"([\w ]+) \(qty=([1-9]\d*)\)", prompt)
    if alt_hit:
        return (
            f"mock heuristic: proceed with alternative {alt_hit.group(1).strip()!r} "
            f"(qty={alt_hit.group(2)}); the originally requested part has no stock."
        )
    return (
        "mock heuristic: delay the job -- neither the requested part nor any "
        "alternative has stock, and this system has no supplier-availability "
        "tool to check next."
    )


def _mock_invoke(prompt: str) -> str:
    """Issue 5 -- dispatches every plain `llm.invoke()` call (the only
    interface planning/vendor/planning_lab/algorithms/{self_refine,
    reflexion}.py use; neither has a with_structured_output() schema, see
    _mock_structured's docstring below) to a heuristic matching which of
    the four distinct prompts self_refine/reflexion actually send --
    identified by the fixed phrasing those vendored files themselves
    write, not guessed. Falls back to _mock_synthesis (Issue 3's
    proceed/alternative/delay heuristic) for everything else -- i.e.
    plan_and_solve.py's and lats.py's own invoke() calls, unchanged from
    before Issue 5."""
    if "Episodic memory from previous failed trials:" in prompt:
        return _mock_reflexion_attempt(prompt)
    if "State what I did wrong and the specific strategy" in prompt:
        return _mock_reflexion_reflection(prompt)
    if "List concrete issues. If there are none, respond exactly PASS." in prompt:
        return _mock_self_refine_critique(prompt)
    if "Return only the improved deliverable." in prompt:
        return _mock_self_refine_revise(prompt)
    return _mock_synthesis(prompt)


def _mock_self_refine_critique(prompt: str) -> str:
    """Issue 5 -- offline stand-in for self_refine.py's critic call.
    self_refine.reflect_and_refine() already computes REAL deterministic
    checks (deterministic_checks(), grounded in the draft's own word
    count/goal-term overlap/structure -- not an LLM opinion) and embeds
    them in the prompt as 'External deterministic checks:\\n...'. This
    mock only echoes that real, already-grounded report back as the
    critique instead of inventing a separate one -- same 'don't fabricate
    what's already grounded' philosophy as planning/grounded_environment.py."""
    match = re.search(r"External deterministic checks:\n(.*?)\n\nDraft:", prompt, re.DOTALL)
    checks = match.group(1).strip() if match else ""
    if checks == "- Deterministic checks passed.":
        return "PASS"
    return f"mock heuristic critique -- deterministic checks found:\n{checks}"


def _mock_self_refine_revise(prompt: str) -> str:
    """Issue 5 -- offline stand-in for self_refine.py's revision call.
    Turns the original draft into a short structured list (fixes the
    real 'no visible structure' check) and repeats the goal in an
    explicit heading (fixes the real 'none of the goal's significant
    terms' check) -- addressing the SAME concrete, already-grounded
    issues the critique surfaced, not inventing new content."""
    draft_match = re.search(r"Draft:\n(.*?)\n\nGrounded checks:", prompt, re.DOTALL)
    goal_match = re.search(r"^Goal: (.*?)\n\nDraft:", prompt, re.DOTALL)
    draft = draft_match.group(1).strip() if draft_match else prompt.strip()
    goal = goal_match.group(1).strip() if goal_match else "this update"
    return (
        f"## {goal}\n\n"
        f"- {draft}\n"
        "- This was checked for completeness and clarity before sending.\n"
        f"- Reply to this message if anything about {goal} needs follow-up."
    )


def _mock_reflexion_attempt(prompt: str) -> str:
    """Issue 5 -- offline stand-in for reflexion.py's acting-agent call.
    Reuses _mock_synthesis's real findings-parsing heuristic UNLESS a
    prior trial's reflection (see _mock_reflexion_reflection) left a
    'remembered lesson: verified alternative ...' marker in the episodic
    memory this prompt embeds -- in which case it obeys that lesson,
    demonstrating a reflection actually changing the next trial's
    output, not just being generated and ignored."""
    lesson = re.search(r"remembered lesson: verified alternative '([^']+)' \(qty=(\d+)\)", prompt)
    if lesson:
        name, qty = lesson.group(1), lesson.group(2)
        return (
            f"mock heuristic (reflexion, applying remembered lesson): proceed with "
            f"alternative {name!r} (qty={qty}); verified in stock per the previous "
            "trial's grounded feedback."
        )
    return _mock_synthesis(prompt)


def _mock_reflexion_reflection(prompt: str) -> str:
    """Issue 5 -- offline stand-in for reflexion.py's reflection call.
    Does not invent which alternative is real -- re-reads the SAME real
    '<name> (qty=N)' findings pairs already present in this trial's own
    Task text (the real facts Issue 2's altsearch step put there), and
    names the first one that was NOT the failed attempt itself, so the
    next trial has a genuinely different, grounded candidate to try.
    Falls back to recommending delay when nothing else is available."""
    failed_match = re.search(r"Failed attempt:\n(.*?)\n\nExternal environment feedback", prompt, re.DOTALL)
    failed_attempt = (failed_match.group(1) if failed_match else "").lower()
    pairs = re.findall(r"([\w][\w ]*?) \(qty=([1-9]\d*)\)", prompt)
    candidate = next((pair for pair in pairs if pair[0].strip().lower() not in failed_attempt), None)
    if candidate:
        name, qty = candidate[0].strip(), candidate[1]
        return (
            "I proposed a candidate the grounded environment rejected. Next trial, "
            f"remembered lesson: verified alternative '{name}' (qty={qty}) -- I should "
            "check the real database before proposing anything else."
        )
    return (
        "I proposed a candidate the grounded environment rejected, and no other "
        "stocked option appears in the findings. Next trial, I should recommend "
        "delay instead of guessing again."
    )


def _mock_structured(schema, prompt: str):
    if schema.__name__ == "DynamicDecision":
        return _mock_dynamic_decision(schema, prompt)
    if schema.__name__ == "ThoughtCandidates":
        return _mock_thought_candidates(schema, prompt)
    if schema.__name__ == "ThoughtEvaluation":
        return _mock_thought_evaluation(schema, prompt)
    if schema.__name__ == "LATSActionBatch":
        return _mock_lats_action_batch(schema, prompt)
    if schema.__name__ == "ValueEstimate":
        return _mock_value_estimate(schema, prompt)
    # Self-Refine/Reflexion (Issue 5) never reach this function: confirmed
    # by inspecting planning/vendor/planning_lab/algorithms/{self_refine,
    # reflexion}.py -- both call only llm.invoke(), never
    # with_structured_output(). Their offline mocks live in _mock_invoke()
    # above instead. This branch stays a hard failure for any OTHER
    # not-yet-supported schema, instead of guessing a shape.
    raise NotImplementedError(
        f"No offline mock defined for {schema.__name__} yet -- that "
        f"belongs to a later Issue; add its mock there, don't guess one here."
    )


def _mock_dynamic_decision(schema, prompt: str):
    """Heuristic stand-in for the dynamic loop's 'what's next' decision.
    Same style as mcp-server/rag/llm_client.py's _mock_decision: scans
    prompt text this repo's own code constructed, deterministic."""
    remaining_match = re.search(r"remaining required parts: \[(.*?)\]", prompt)
    remaining = (
        [p.strip(" '\"") for p in remaining_match.group(1).split(",") if p.strip(" '\"")]
        if remaining_match
        else []
    )
    pending_match = re.search(r"pending alternative search: (.+?)(?=\n|$)", prompt)
    pending = pending_match.group(1).strip() if pending_match and pending_match.group(1).strip() != "None" else None

    if pending:
        return schema(done=False, next_task=f"altsearch:{pending}")
    if remaining:
        return schema(done=False, next_task=f"check:{remaining[0]}")
    return schema(done=True, next_task="")


def _mock_thought_candidates(schema, prompt: str):
    """Issue 3 -- Tree of Thoughts candidate generation. Reads the real
    '<name> (qty=<n>)' pairs planning/fulfillment_planning.py put in the
    prompt (see select_best_alternative) and proposes one candidate per
    alternative, ranked by declared quantity -- deterministic, not
    random, same philosophy as the rest of this file."""
    pairs = re.findall(r"([\w][\w ]*?) \(qty=(\d+)\)", prompt)
    if not pairs:
        return schema(candidates=["Proceed with the best available option"])
    ranked = sorted(pairs, key=lambda pair: -int(pair[1]))[:3]
    return schema(candidates=[f"Use {name.strip()} (qty={qty})" for name, qty in ranked])


def _mock_thought_evaluation(schema, prompt: str):
    """Issue 3 -- Tree of Thoughts candidate scoring. Parses the
    candidate's own '(qty=N)' back out of the prompt so higher-stocked
    alternatives score higher -- grounded in the number actually in the
    candidate text, not a guess."""
    match = re.search(r"\(qty=(\d+)\)", prompt.split("Candidate path:")[-1])
    qty = int(match.group(1)) if match else 0
    score = round(min(1.0, qty / 10.0), 4)
    return schema(score=score, rationale=f"mock heuristic: higher stocked quantity ({qty}) scores higher")


def _mock_lats_action_batch(schema, prompt: str):
    """Issue 3 -- LATS action proposal. Reuses _mock_synthesis's real
    proceed/alternative/delay heuristic (same findings text is embedded
    in the LATS task prompt) as one candidate, and always offers a
    second, clearly-worse candidate so the search has something to
    reject -- keeps this deterministic rather than inventing a
    free-form LLM brainstorm offline."""
    primary = _mock_synthesis(prompt)
    if "delay" in primary.lower():
        secondary = "Proceed anyway without checking stock again."
    else:
        secondary = "Delay the job without checking any alternative first."
    return schema(
        actions=[
            {"action": "mock_primary_recommendation", "state": primary},
            {"action": "mock_alternative_recommendation", "state": secondary},
        ]
    )


def _mock_value_estimate(schema, prompt: str):
    """Issue 3 -- LATS value function. Mirrors the environment's own
    score back (the prompt always contains 'External score: <n>' per
    vendor/planning_lab/algorithms/lats.py) rather than inventing an
    independent opinion -- an honest offline stand-in agrees with the
    grounded/ungrounded signal it's given, it doesn't override it."""
    match = re.search(r"External score: ([0-9.]+)", prompt)
    score = float(match.group(1)) if match else 0.5
    return schema(score=round(min(max(score, 0.0), 1.0), 4))
