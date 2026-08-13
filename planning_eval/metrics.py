"""
planning_eval/metrics.py

Issue 7. A thin, transparent counting layer around whatever
planning.model_provider.get_llm() returns (real langchain_anthropic.
ChatAnthropic or the offline heuristic double) so every planning_eval run
reports real LLM-call counts, real latency, and token counts -- real
when using the real Anthropic API (via LangChain's own `.usage_metadata`
on the response), a clearly-labelled word-count approximation when
running offline (no ANTHROPIC_API_KEY), same "real-or-mock, never
silently fake" convention as planning/model_provider.py itself.

Does not change planning/model_provider.get_llm() or the vendored
toolkit -- this wraps around the BaseChatModel-compatible object those
already return, same "seam, not a rewrite" approach as the rest of
planning/.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass


def _approx_tokens(text: str) -> int:
    """Offline-only estimate (no tokenizer dependency added for this):
    ~1.3 tokens per whitespace-split word, the same rough ratio commonly
    quoted for English text. Only used when the real API's own
    usage_metadata isn't available (offline mode) -- flagged via
    CallLog.token_source so the comparison table never presents this as
    a real measurement."""
    if not text:
        return 0
    return max(1, round(len(text.split()) * 1.3))


@dataclass
class CallLog:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_seconds: float = 0.0
    token_source: str = "offline-estimate"  # or "real-usage-metadata"
    cost_usd: float | None = None


def _calculate_cost(input_tokens: int, output_tokens: int) -> float | None:
    """Calculate USD cost only when explicit per-million-token prices are configured.

    Defaults are intentionally absent so an offline/mock run can never silently
    claim a dollar cost. Set PLANNING_INPUT_USD_PER_1M and
    PLANNING_OUTPUT_USD_PER_1M for the model actually used.
    """
    try:
        input_rate = float(os.getenv("PLANNING_INPUT_USD_PER_1M", ""))
        output_rate = float(os.getenv("PLANNING_OUTPUT_USD_PER_1M", ""))
    except ValueError:
        return None
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def _refresh_cost(log: CallLog) -> None:
    if log.token_source == "real-usage-metadata":
        log.cost_usd = _calculate_cost(log.input_tokens, log.output_tokens)
    else:
        log.cost_usd = None


class _StructuredProxy:
    def __init__(self, inner, log: CallLog):
        self._inner = inner
        self._log = log

    def invoke(self, messages, **kwargs):
        start = time.perf_counter()
        result = self._inner.invoke(messages, **kwargs)
        self._log.latency_seconds += time.perf_counter() - start
        self._log.calls += 1
        # Structured-output responses are validated pydantic objects, not
        # BaseMessage -- no usage_metadata to read here in either mode, so
        # this branch always uses the documented estimate.
        prompt_text = messages[-1][1] if messages else ""
        in_tok = _approx_tokens(prompt_text)
        out_tok = _approx_tokens(str(result))
        self._log.input_tokens += in_tok
        self._log.output_tokens += out_tok
        self._log.total_tokens += in_tok + out_tok
        _refresh_cost(self._log)
        return result


class InstrumentedLLM:
    """Drop-in BaseChatModel-compatible wrapper (.invoke /
    .with_structured_output) that tallies real call counts, latency, and
    tokens as a side effect -- every planning_eval harness function
    passes ONE of these instead of a raw get_llm() so every table row's
    calls/tokens/latency column is a real measurement of that specific
    run, not a hand-written estimate."""

    def __init__(self, llm=None):
        from planning.model_provider import get_llm

        self._llm = llm or get_llm()
        self.log = CallLog()

    def invoke(self, messages, **kwargs):
        start = time.perf_counter()
        result = self._llm.invoke(messages, **kwargs)
        self.log.latency_seconds += time.perf_counter() - start
        self.log.calls += 1
        usage = getattr(result, "usage_metadata", None)
        prompt_text = messages[-1][1] if messages else ""
        if usage:
            self.log.token_source = "real-usage-metadata"
            self.log.input_tokens += usage.get("input_tokens", 0)
            self.log.output_tokens += usage.get("output_tokens", 0)
            self.log.total_tokens += usage.get(
                "total_tokens", usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            )
            _refresh_cost(self.log)
        else:
            in_tok = _approx_tokens(prompt_text)
            out_tok = _approx_tokens(getattr(result, "content", str(result)))
            self.log.input_tokens += in_tok
            self.log.output_tokens += out_tok
            self.log.total_tokens += in_tok + out_tok
            _refresh_cost(self.log)
        return result

    def with_structured_output(self, schema, *, method):
        inner = self._llm.with_structured_output(schema, method=method)
        return _StructuredProxy(inner, self.log)


def fresh_llm() -> InstrumentedLLM:
    """One instrumented LLM per measured run -- callers must not share
    one InstrumentedLLM across two rows of the comparison table, or the
    tallies would mix two methods' calls together."""
    return InstrumentedLLM()


__all__ = ["CallLog", "InstrumentedLLM", "fresh_llm"]
