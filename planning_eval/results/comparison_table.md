| Concern | Case | Method | Success | LLM calls | Tool calls | Total tokens (source) | Latency (s) | Detail |
|---|---|---|---|---|---|---|---|---|
| decomposition | decomp_first_favored | decomposition-first | success | 1 | 10 | 63 (offline-estimate) | 0.0162 | mock heuristic: proceed with alternative 'Brake Disc XL' (qty=4); the originally requested part has no stock. |
| decomposition | decomp_first_favored | dynamic-decomposition | success | 5 | 10 | 276 (offline-estimate) | 0.0155 | mock heuristic: proceed with alternative 'Brake Disc XL' (qty=4); the originally requested part has no stock. |
| decomposition | dynamic_favored | decomposition-first | success | 1 | 8 | 59 (offline-estimate) | 0.0096 | mock heuristic: proceed with the originally requested part (found positive stock -- Spark Plug: id=20 quantity=25). |
| decomposition | dynamic_favored | dynamic-decomposition | success | 4 | 7 | 207 (offline-estimate) | 0.0096 | mock heuristic: proceed with the originally requested part (found positive stock -- check:Spark Plug: Spark Plug: id=20  |
| planning-algorithm | lookahead_needed | plan-and-solve | fail | 1 | 0 | 79 (offline-estimate) | 0.0003 | mock heuristic: proceed with alternative 'Radiator Hose Std' (qty=3); the originally requested part has no stock. |
| planning-algorithm | lookahead_needed | tree-of-thoughts | success | 3 | 0 | 270 (offline-estimate) | 0.0005 | Use Radiator Hose Heavy Duty (qty=9) (score=0.9) |
| grounding | reflexion_needed | lats-ungrounded | success | 2 | 0 | 268 (offline-estimate) | 0.0013 | best_score=0.8412 fabricated_accepted=True |
| grounding | reflexion_needed | lats-grounded | success | 4 | 1 | 559 (offline-estimate) | 0.0028 | best_score=0.7 fabricated_accepted=False |
| self-correction | reflexion_needed | single-retry (max_trials=1) | fail | 2 | 0 | 305 (offline-estimate) | 0.0031 | trials=1 |
| self-correction | reflexion_needed | reflexion (max_trials=3) | success | 3 | 0 | 467 (offline-estimate) | 0.0070 | trials=2 |
| self-correction | reflexion_needed | self-refine (notification) | success | 3 | 0 | 594 (offline-estimate) | 0.0016 | revised != draft: True |
