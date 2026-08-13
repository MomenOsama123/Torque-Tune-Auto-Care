"""
context_eval/strategies.py

Four context-window management strategies. Each takes the SAME raw
transcript (list of message dicts, same role/content/metadata schema as
mcp-server/memory/short_term_memory.py's Message) and returns:

    (pruned_messages, extra_input_tokens, extra_output_tokens, extra_latency_s)

`extra_*` is the cost the pruning *operation itself* adds on top of the
final answer call (nonzero only for recursive_summarization, which makes
its own LLM calls to compact old turns -- the other three are pure
Python and add no LLM cost).

This is a different concern from mcp-server/memory/router.py: the router
decides forget-vs-promote-to-episodic when the *live* short-term buffer
overflows. These strategies decide what to keep in the LLM's working
context for one long transcript. Neither one writes to episodic or
semantic memory.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

RAG_DIR = Path(__file__).resolve().parents[1] / "mcp-server" / "rag"
if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))

from llm_client import llm_call, _API_KEY, _approx_tokens  # noqa: E402

Message = Dict[str, Any]
PruneResult = Tuple[List[Message], int, int, float]


def _render(msg: Message) -> str:
    return f"[{msg['role']}] {msg['content']}"


# ---------------------------------------------------------------------
# 1. Sliding window
# ---------------------------------------------------------------------
def sliding_window(transcript: List[Message], window: int = 10) -> PruneResult:
    """Keep only the last `window` messages. Cheapest strategy, zero LLM
    calls -- but anything before the window is gone for good, including a
    critical detail stated once near the start and never repeated."""
    return transcript[-window:], 0, 0, 0.0


# ---------------------------------------------------------------------
# 2. Observation / tool-output masking
# ---------------------------------------------------------------------
def observation_masking(transcript: List[Message], keep_last_tool_pairs: int = 3) -> PruneResult:
    """Keep every user/assistant turn untouched -- dialogue is where
    decisions and commitments get stated, and it's cheap. Only the
    `keep_last_tool_pairs` most recent tool_call/tool_output pairs are
    kept in full; older tool JSON is replaced with a one-line
    placeholder. Targets Torque Tune's real bloat source: a stock check
    or alternative-parts lookup returns a wall of JSON, not the chat."""
    tool_indices = [i for i, m in enumerate(transcript) if m["role"] in ("tool_call", "tool_output")]
    keep_from = set(tool_indices[-(keep_last_tool_pairs * 2):]) if tool_indices else set()

    pruned: List[Message] = []
    for i, m in enumerate(transcript):
        if m["role"] in ("tool_call", "tool_output") and i not in keep_from:
            tool_name = (m.get("metadata") or {}).get("tool", "tool")
            pruned.append({
                "role": m["role"],
                "content": f"[masked -- {tool_name} call, {len(str(m['content']))} chars omitted]",
                "metadata": m.get("metadata"),
            })
        else:
            pruned.append(m)
    return pruned, 0, 0, 0.0


# ---------------------------------------------------------------------
# 3. Recursive summarization
# ---------------------------------------------------------------------
_FLAG_KEYWORDS = [
    "warranty", "declined", "recall", "safety", "airbag", "towing",
    "heavy-duty", "complain", "reported", "still under", "no charge",
    "covered", "prior visit", "last visit", "already paid", "ask me first",
]


def _summarize_chunk(chunk_text: str, running_summary: str) -> Tuple[str, int, int]:
    system = (
        "You are compacting a service-desk conversation transcript for an "
        "auto-repair shop into a running summary. Preserve any "
        "customer-stated facts that could affect billing, safety, or parts "
        "decisions (warranties, declined services, recalls, symptoms, usage "
        "details). Drop routine tool-call noise. Keep it to 2-4 sentences total."
    )
    user = f"Running summary so far:\n{running_summary or '(none)'}\n\nNew chunk:\n{chunk_text}"
    if _API_KEY:
        return llm_call(system, user)

    # Offline fallback: extractive, not a language model -- same documented
    # pattern as rag/llm_client.py's mock responder. Keeps sentences that
    # mention a flagged fact class verbatim rather than paraphrasing, so
    # this measures the *strategy's* cost/behavior honestly instead of
    # faking a real model's output.
    sentences = re.split(r"(?<=[.!?])\s+", chunk_text)
    kept = [s.strip() for s in sentences if any(k in s.lower() for k in _FLAG_KEYWORDS)]
    body = " ".join(kept) if kept else "(routine turns, nothing flagged)"
    text = f"{running_summary} {body}".strip()
    return text, _approx_tokens(system + user), _approx_tokens(text)


def recursive_summarization(
    transcript: List[Message], chunk_size: int = 15, keep_raw_last: int = 10
) -> PruneResult:
    """Compact the transcript chunk_size messages at a time into a running
    summary, keeping only the last `keep_raw_last` messages raw. The only
    strategy here that makes its own LLM calls -- costs the most output
    tokens and latency of the four, in exchange for not needing a fixed
    keep-window."""
    raw_tail = transcript[-keep_raw_last:]
    to_summarize = transcript[:-keep_raw_last] if keep_raw_last < len(transcript) else []

    if not to_summarize:
        return raw_tail, 0, 0, 0.0

    summary_text = ""
    total_in = 0
    total_out = 0
    for start in range(0, len(to_summarize), chunk_size):
        chunk = to_summarize[start:start + chunk_size]
        chunk_text = "\n".join(_render(m) for m in chunk)
        summary_text, in_tok, out_tok = _summarize_chunk(chunk_text, summary_text)
        total_in += in_tok
        total_out += out_tok

    summary_msg: Message = {
        "role": "system",
        "content": f"[summary of earlier turns] {summary_text}",
        "metadata": {"synthetic": True},
    }
    return [summary_msg] + raw_tail, total_in, total_out, 0.0


# ---------------------------------------------------------------------
# 4. Zone-based pruning
# ---------------------------------------------------------------------
_COMMITMENT_KEYWORDS = _FLAG_KEYWORDS  # same business-rule categories: compliance/financial/safety facts


def zone_based_pruning(
    transcript: List[Message], recent_window: int = 8
) -> PruneResult:
    """Classify every message into one of four zones by a fixed rule, not
    by position alone and not by looking at the test question:
      A. Commitment zone (warranty/recall/decline/safety/usage facts) --
         pinned, kept verbatim regardless of age.
      B. Recent zone (last `recent_window` messages) -- kept raw.
      C. Tool-noise zone (tool_call/tool_output, not recent, not a
         commitment) -- compacted to a one-line marker.
      D. Routine dialogue zone (old user/assistant turns, not a
         commitment) -- compressed to their first sentence.
    """
    n = len(transcript)
    pruned: List[Message] = []
    for i, m in enumerate(transcript):
        content = str(m["content"])
        content_l = content.lower()
        is_recent = i >= n - recent_window
        is_commitment = m["role"] in ("user", "assistant") and any(
            k in content_l for k in _COMMITMENT_KEYWORDS
        )
        is_tool = m["role"] in ("tool_call", "tool_output")

        if is_commitment:
            pruned.append(m)  # Zone A: pinned
        elif is_recent:
            pruned.append(m)  # Zone B: recent, kept raw
        elif is_tool:
            tool_name = (m.get("metadata") or {}).get("tool", "tool")
            pruned.append({
                "role": m["role"],
                "content": f"[tool noise summarized -- {tool_name}]",
                "metadata": m.get("metadata"),
            })  # Zone C
        else:
            first_sentence = re.split(r"(?<=[.!?])\s+", content)[0]
            pruned.append({"role": m["role"], "content": first_sentence, "metadata": m.get("metadata")})  # Zone D

    return pruned, 0, 0, 0.0
