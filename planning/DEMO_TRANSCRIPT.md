# Week 4 Planning Demo Transcript

This transcript is the evidence checklist for the final demo. It is intentionally
short: each section maps to a rubric requirement and points to the implementation
that produces the behavior. Run the commands below from the repository root.

## 1. Decomposition-first vs Dynamic divergence

Command:

```bash
python planning/fulfillment_demo.py
```

Scenario: a repair job contains a required part whose stock is zero while another
part has positive stock.

Expected evidence:
- decomposition-first creates the alternative-search branch up front;
- dynamic decomposition checks the current stock first and skips that branch when
  the requested part is already in stock;
- both methods use the real inventory read tools rather than invented tool results.

## 2. Live agent integration

Entry point: `agent/client.py -> handle_user_request()`.

Expected routing:

```text
repair / spare-parts request
        -> planning route
        -> decomposition
        -> Plan-and-Solve / ToT / LATS
        -> grounded environment
        -> result written to the same session memory

ordinary request
        -> existing Memory/RAG route
```

The planning route therefore runs alongside, not instead of, Memory/RAG.

## 3. Planning algorithm routing

The final planning workflow routes sub-tasks by characteristics:

- notification/mechanical sub-task -> Plan-and-Solve
- multiple stocked alternatives -> Tree of Thoughts
- high-impact final decision -> LATS

Evidence: `planning/routing.py` and `planning/fulfillment_planning.py`.

## 4. Grounded failure rejection

Command:

```bash
python planning_eval/run_eval.py
```

Scenario: `reflexion_needed` includes a candidate that the model can propose but
that is not present as a valid in-stock alternative in the real scenario DB.

Expected evidence:
- ungrounded LATS can accept the fabricated candidate;
- grounded LATS checks the database through the real inventory tools;
- the fabricated candidate is rejected (`fabricated_accepted=False`).

## 5. Self-Refine

The evaluation runs a draft -> critique -> revision sequence for the customer
notification. The final row must show `revised != draft: True`.

Implementation: `planning/self_correction.py`.

## 6. Reflexion

The evaluation runs a failed first trial, stores the reflection, then performs a
second trial using the remembered lesson. The final row must show `trials=2` and
success.

Implementation: `planning/self_correction.py`.

## 7. Final evaluation evidence

The generated comparison table must contain:

- Success
- LLM calls
- Tool calls
- Total tokens + token source
- Latency
- Cost (USD)

For the final submission, run with `ANTHROPIC_API_KEY` configured so token usage
comes from Claude usage metadata. Configure the model's actual input/output prices
using `PLANNING_INPUT_USD_PER_1M` and `PLANNING_OUTPUT_USD_PER_1M`.

Never present offline token estimates as live API measurements.
