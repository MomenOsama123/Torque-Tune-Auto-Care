# Context Window Management Comparison

## The problem

Torque Tune's longest live sessions are diagnostic/service-writer calls:
a customer states one fact early (a warranty, a recall, a prior declined
service, a usage detail that changes which part is correct) and the agent
then spends the rest of the call round-tripping the inventory tools
(`check_stock`, `suggest_alternative`) before a final question depends on
that early fact. Nothing about the existing `mcp-server/` tools or
`memory/` buffer decides what to keep once a transcript gets long -- that's
the gap this closes.

## What was built (`context_eval/`)

| File | Role |
|---|---|
| `transcripts.py` | 5 fixed long-context test transcripts, each a ~35-45 message service call: one critical customer-stated fact near the start, 14-20 `tool_call`/`tool_output` pairs of realistic inventory-lookup JSON burying it, then a final question that depends on it |
| `strategies.py` | All four strategies, each taking the same raw transcript and returning a pruned context: **sliding window** (last N messages), **observation masking** (keep all dialogue, mask old tool JSON), **recursive summarization** (LLM-compacted running summary of old chunks + raw recent tail), **zone-based pruning** (4 rule-based zones: pinned commitment facts, recent-raw, tool-noise, compressed old dialogue) |
| `run_eval.py` | Runs all four against the same 5 transcripts, feeds the pruned context + final question through the same `llm_client` seam `rag/` uses, and checks whether the critical detail survived into the answer |

## Comparison table

5 long-context test transcripts, run via `python context_eval/run_eval.py`:

| Strategy | Detail recalled | Avg input tokens | Avg output tokens | Avg latency |
|---|---|---|---|---|
| Sliding window (last 10 msgs) | 0/5 | 585 | 98 | 0.0003s |
| Observation masking | 4/5 | 974 | 70 | 0.0005s |
| Recursive summarization | 4/5 | 2,216 | 202 | 0.0006s |
| Zone-based pruning | 4/5 | 974 | 70 | 0.0005s |

## Chosen strategy: observation masking

Sliding window fails outright (0/5): every transcript's critical fact is
stated in the first 4 messages and pushed out by 14-20 tool-call pairs long
before the last-10-messages window would reach it. This matches the actual
shape of Torque Tune's bloat -- it's tool JSON, not dialogue -- so a
strategy that drops dialogue on a fixed schedule is the wrong tool.

Observation masking and zone-based pruning tie on both recall (4/5) and
cost, because for these transcripts they end up doing nearly the same
thing: zone-based pruning's "pinned commitment" zone is a superset of what
observation masking gets for free by never touching dialogue at all, and
its tool-noise zone compacts the same JSON observation masking already
masks. Given the identical outcome, **observation masking ships** as the
simpler mechanism -- one rule (mask old tool output, never dialogue)
instead of four zone-classification rules to maintain.

Recursive summarization matches their recall (4/5) but at **~2.3x the
input tokens and ~2.9x the output tokens**, because it's the only strategy
making its own LLM calls to compact old chunks. That cost only pays for
itself if a transcript needs to be shrunk (a whole 40-turn transcript
truly can't fit in the model's window); Torque Tune's transcripts are long
in message count but not in raw size, so masking already solves the
problem without paying for extra generation.

All three non-sliding strategies miss the same transcript (T5), and for
two different reasons worth separating:

- **Recursive summarization and zone-based pruning miss T5 because they
  genuinely drop the detail.** The daughter's air-freshener allergy isn't
  a warranty/recall/declined-service/safety fact, so it doesn't match the
  fixed keyword categories either strategy uses to decide what's worth
  preserving, and it isn't the first sentence of its message (so
  zone-based pruning's generic-dialogue compression cuts it). This is a
  real, honest limitation: any strategy that classifies importance by a
  fixed rule set will miss facts outside those categories.
- **Observation masking misses T5 for a different reason: the fact
  survives pruning but the answer step doesn't surface it.** The pruned
  context does contain the allergy sentence (verified directly against
  `strategies.py` output), but this environment has no configured
  `ANTHROPIC_API_KEY`, so the final-answer step runs through
  `llm_client.py`'s documented extractive mock, which scores sentences by
  raw keyword overlap with the question. The question ("anything special
  we should do or avoid...") shares almost no vocabulary with the answer
  sentence ("...allergic to the pine air freshener..."), so the mock
  never selects it even though it's right there in context. A real LLM
  call would very likely catch this one; the mock's failure here is a
  property of the mock's answer-extraction heuristic, not of the pruning
  strategy, and is the same caveat `retrieval_eval/README_SECTION.md`
  notes about answer-accuracy numbers under the mock.

That distinction is also the argument for observation masking over the
keyword-based strategies in production: once a real LLM is answering
instead of the mock, observation masking's advantage is that it never
had to *decide in advance* which fact classes matter -- it preserves all
customer-stated facts by construction, so it isn't blind to anything
outside a fixed keyword list the way recursive summarization and
zone-based pruning are.

*Note on token/latency numbers: `ANTHROPIC_API_KEY` is not configured in
this environment, so recursive summarization's compaction calls and the
final-answer call both run through `llm_client.py`'s mock path
(char-count-based token estimate). Relative ordering between strategies
(masking/zone cheaper than summarization; summarization triples output
tokens) will hold with a real key; absolute token counts will differ.*
