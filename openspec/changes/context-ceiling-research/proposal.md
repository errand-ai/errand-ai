## Why

`max_context_tokens` defaults to 150,000. That number was chosen before there was any measurement to choose it from, and the production data now available suggests it is not obviously right in either direction.

Capability and latency give opposite answers. gemma-4 26B reports a 260,352-token window, so 150,000 leaves most of the model unused. But every turn re-prefills the whole context, so on local hardware latency binds long before capability does — a larger ceiling would mean slower turns, not more headroom. Measured peak across 216 production tasks is 142,623 tokens (95.1% of the ceiling), which says the current value is being reached but not exceeded, and does not by itself say whether that is comfortable or lucky.

This is an investigation with no predetermined code outcome, which is why it is scoped separately from the two changes that do have one.

## What Changes

- **Decide the right ceiling from evidence.** Weigh capability against latency using the `llm_turn_end` series, which carries `duration_ms` alongside `input_tokens` — the cost of a larger context is already being measured, per turn, and can be quantified rather than assumed.
- **Resolve a model's true context window automatically.** Today the ceiling is a hand-set number that has no relationship to the model actually serving the task. It is resolvable: LiteLLM `/model/info` gives the provider `api_base`, and LM Studio exposes `max_context_length`. Note `errand/model_metadata.py` already downloads `model_prices_and_context_window.json` and reads only two fields from it, so part of the plumbing exists.
- **Determine whether the ceiling should be per-model rather than global.** It is currently one setting for every task regardless of which model runs it, which cannot be right once the window is resolvable per model. Whether that becomes a per-profile override, a resolved default, or stays global is the question this change answers.

## Capabilities

### New Capabilities

- `model-context-window-resolution`: resolving a model's true context window from the provider, and deciding how that interacts with the configured ceiling. Provisional — if the investigation concludes the ceiling should stay hand-set, this capability is not created and the change lands as a decision record only.

### Modified Capabilities

- `task-profile-model`: only if the conclusion is a per-model or per-profile ceiling. Left provisional until the research settles it.

## Impact

- Primarily investigation: querying the existing `llm_turn_end` series for the latency/context relationship, and probing LiteLLM and LM Studio for window metadata.
- `errand/model_metadata.py` if window resolution is adopted.
- `errand/task_manager.py` and the `max_context_tokens` setting if the ceiling stops being a single global value.
- Deliberately no implementation commitment. The output may be a decision to leave the default at 150,000, which is a valid and useful result.
