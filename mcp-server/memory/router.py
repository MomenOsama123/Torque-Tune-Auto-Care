"""
mcp-server/memory/router.py

The promote-or-drop decision layer. Fires only when Short-Term Memory
overflows (see memory_manager.add_interaction). For each aging message it
decides "promote" (-> episodic memory) or "drop" (discarded), with a reason
logged for every decision.

Strict rule this file enforces: this router NEVER writes to Semantic
Memory, directly or indirectly. It only ever returns decisions;
memory_manager.py is the one that calls episodic.add_episode() for
"promote" results. Semantic memory is only ever touched by a separate,
periodic consolidation pass (see semantic_memory.py / run_consolidation.py).

Uses the same LLM seam the RAG layer uses (rag/llm_client.py): a real
Claude call when ANTHROPIC_API_KEY is set, otherwise a documented keyword
mock so this is runnable/gradable offline. See llm_client.py's
_mock_promote_or_drop for exactly what the mock does.
"""

import json
from typing import List, Any, Literal
from dataclasses import dataclass
from .short_term_memory import Message

try:
    from rag.llm_client import llm_call
except ImportError:  # pragma: no cover - path fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rag.llm_client import llm_call


SYSTEM_PROMPT = (
    "You triage short-term conversation memory for an auto-parts inventory "
    "assistant. For each numbered message, decide 'promote' if it carries a "
    "durable customer preference, a decision, a stated failure, a warranty "
    "or allergy/safety detail, or anything else worth remembering after this "
    "session ends. Decide 'drop' for routine tool chatter and filler. "
    "Return ONLY a JSON array of objects: "
    '{"index": <int>, "decision": "promote"|"drop", "reason": "<short reason>"}.'
)


@dataclass
class RouterDecision:
    """The router's decision for a specific piece of short-term memory."""
    decision: Literal["promote", "drop"]
    reason: str
    content: Any


class PromoteOrDropRouter:
    """
    Evaluates messages from Short-Term Memory when it reaches capacity.
    Decides whether to promote information to Episodic Memory or drop it.
    Strict rule: this router NEVER writes directly to Semantic Memory.
    """

    def __init__(self, llm_client=None):
        # Accepted for backward compatibility / dependency injection in
        # tests; actual calls go through rag.llm_client's shared seam so
        # the router and the RAG layer share one real-vs-mock switch.
        self.llm_client = llm_client

    def evaluate_context(self, messages: List[Message]) -> List[RouterDecision]:
        """Analyzes a batch of messages from STM and outputs routing decisions,
        one per message, in the same order they were passed in."""
        if not messages:
            return []

        formatted_context = self._format_for_llm(messages)
        user_prompt = f"promote_or_drop\n\n{formatted_context}"

        raw_text, _in_tok, _out_tok = llm_call(SYSTEM_PROMPT, user_prompt, want_json=True)

        try:
            parsed = json.loads(raw_text)
            by_index = {int(item["index"]): item for item in parsed}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Fail safe: if the model/mock returned something unparseable,
            # promote everything rather than silently losing it, and say why.
            by_index = {}

        decisions: List[RouterDecision] = []
        for i, msg in enumerate(messages):
            item = by_index.get(i)
            if item is not None:
                decisions.append(RouterDecision(
                    decision=item.get("decision", "promote"),
                    reason=item.get("reason", "no reason returned"),
                    content=msg.content,
                ))
            else:
                decisions.append(RouterDecision(
                    decision="promote",
                    reason="fail-safe: router response missing/unparseable for this message, promoting rather than risking silent loss",
                    content=msg.content,
                ))
        return decisions

    def _format_for_llm(self, messages: List[Message]) -> str:
        """Numbered, role-tagged transcript the prompt (and the mock) parses."""
        return "\n".join(
            f"[{i}] [{msg.role}] {msg.content}" for i, msg in enumerate(messages)
        )

