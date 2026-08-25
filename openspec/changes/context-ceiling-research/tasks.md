## 1. Sequence and setup

- [ ] 1.1 Confirm `context-accounting-correctness` has landed and been deployed. It changes when compaction fires, which changes the context lengths that appear in the data — measuring before it means describing a system that no longer exists
- [ ] 1.2 Branch from `main` as `context-ceiling-research`
- [ ] 1.3 No `VERSION` bump yet. This change may produce no code; bump only if it does

## 2. Cheapest hop first

- [ ] 2.1 Check whether `model_prices_and_context_window.json` — already downloaded by `errand/model_metadata.py`, which reads only two fields from it — carries context window data for the models actually in use
- [ ] 2.2 If it does, the LiteLLM/LM Studio chain may be unnecessary. Establish this before investigating the chain, not after
- [ ] 2.3 Record which models are covered and which are not. Coverage determines whether resolution is viable at all

## 3. Verify the resolution chain (only if 2.2 says it is needed)

- [ ] 3.1 Probe LiteLLM `/model/info` and confirm it returns the provider `api_base` for the models in use
- [ ] 3.2 Probe the provider for `max_context_length` and confirm the value is present and plausible
- [ ] 3.3 Record the cost of the chain: how many calls, how often, and whether it can be cached rather than resolved per task
- [ ] 3.4 Confirm the failure mode is graceful — an unreachable provider must leave the task running on the configured ceiling, not fail it

## 4. The latency question

- [ ] 4.1 Pull the `llm_turn_end` series from Loki: `input_tokens`, `output_tokens` and `duration_ms` per turn, segmented by model
- [ ] 4.2 Plot turn latency against context length, per model. Do not pool across models — hardware, quantisation and architecture all differ, and a pooled curve describes nothing
- [ ] 4.3 Control for `output_tokens`, or state plainly that the curve describes total turn cost rather than prefill cost. Either is defensible; conflating them is not
- [ ] 4.4 Identify whether a knee exists and where it falls relative to 150,000
- [ ] 4.5 Note the confounds that could not be controlled — queueing, hardware contention, concurrent tasks — so the curve is read with its limits attached

## 5. The capability question

- [ ] 5.1 Establish the true window for each model in use. Do not generalise from the single gemma-4 26B figure of 260,352
- [ ] 5.2 Compare against measured peaks: peak `input_tokens` is 142,623 across 216 tasks, with 8 reaching the trigger in 30 days. Establish whether tasks are being compacted that would not need to be
- [ ] 5.3 Establish what compaction costs when it fires — a summarisation call per compaction, plus the fidelity loss — so the benefit of avoiding it is quantified rather than assumed

## 6. Decide

- [ ] 6.1 Decide the ceiling value, with the evidence attached. "Keep 150,000" is a valid and useful outcome
- [ ] 6.2 Decide whether the ceiling stays global. Weigh per-model correctness against the legibility a global value gives: every task compacting at the same point makes the peak-context series from `context-usage-observability` interpretable without a per-row denominator
- [ ] 6.3 If it becomes per-model, decide whether it is an absolute number or a fraction of the resolved window. A fraction tracks the model without a per-model setting
- [ ] 6.4 If it becomes per-model, resolve what governs a task whose model changes between retries
- [ ] 6.5 Confirm the decision in `context-usage-observability` to store the ceiling alongside the peak still holds. It was made partly to survive this change

## 7. Land the outcome

- [ ] 7.1 If the conclusion needs no code: discard the provisional `model-context-window-resolution` spec, record the decision and its evidence, and archive. This is a success, not an abandoned change
- [ ] 7.2 If the conclusion needs code: confirm the provisional spec still matches what was decided, and revise it rather than implementing against a spec written before the evidence existed
- [ ] 7.3 Either way, record the latency curve and the window findings somewhere durable. They are the expensive part and will be wanted again the next time the ceiling is questioned

## 8. Verify

- [ ] 8.1 `openspec validate --specs` passes, as the CI guard requires
- [ ] 8.2 If code landed, backend and task-runner suites green
- [ ] 8.3 If the ceiling changed, compare peak `input_tokens` and compaction frequency against the pre-change baseline and confirm the change had the predicted effect. A ceiling raised on latency evidence that then increases turn latency was raised on the wrong reading
