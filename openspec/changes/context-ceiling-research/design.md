## Context

`max_context_tokens` defaults to 150,000. Nobody measured their way to that number — it predates the telemetry that would have allowed it. Two facts now in hand say it deserves re-examination, and disagree about which direction:

- **Capability says it is too low.** gemma-4 26B reports a 260,352-token window. The ceiling leaves roughly 40% of the model unused, and the ceiling is global, so it applies regardless of which model actually serves the task.
- **Latency says it may be too high.** Every turn re-prefills the whole context. On local hardware, prompt processing time scales with context length, so a larger ceiling buys headroom at the cost of slower turns — and the tasks that would use the headroom are exactly the long ones where turn latency compounds.

Production sits close to the line: peak measured `input_tokens` across 216 tasks is 142,623, or 95.1% of the ceiling, with eight tasks reaching the compaction trigger in 30 days. That says the ceiling is being reached but not exceeded. It does not say whether that is comfortable or lucky.

This change is an investigation. It is scoped separately from the two changes that have a predetermined code outcome precisely because this one does not, and might correctly conclude that 150,000 stays.

## Goals / Non-Goals

**Goals:**

- Quantify the latency cost of context length from data already being collected, rather than assuming it.
- Establish whether a model's true context window is resolvable at runtime, and at what cost.
- Answer whether the ceiling should remain a single global value.
- Produce a decision with its evidence, whether or not it produces code.

**Non-Goals:**

- Committing to raise, lower, or vary the ceiling before the evidence exists.
- Fixing the compaction estimator or the tool-result cap. Those are `context-accounting-correctness`, and both should land first so the measurements here describe a system whose accounting is correct.
- Building a settings surface for whatever is decided. `context-usage-observability` owns the card.

## Decisions

Decisions here are about *how to investigate*, not what to conclude.

### 1. Derive the latency curve from the existing telemetry, not from a benchmark

**Chosen:** use the `llm_turn_end` series, which carries `duration_ms` alongside `input_tokens` on every turn already recorded in Loki.

**Why:** the relationship between context length and turn latency is already being measured, per turn, across every model and every workload in production. A synthetic benchmark would produce cleaner numbers about a situation nobody is actually in. The observed data has confounds — model, output length, queueing, hardware contention — and controlling for them is real work, but it describes the system as it runs.

**Caveat to carry:** `duration_ms` covers the whole call, so output tokens and generation speed are inside it. Isolating prefill cost means either controlling for `output_tokens` (also recorded) or accepting that the curve describes total turn cost, which is arguably the number that matters anyway.

### 2. Probe the window resolution chain before designing around it

**Chosen:** establish that LiteLLM `/model/info` → provider `api_base` → LM Studio `max_context_length` actually works end to end, for the models in use, before any code depends on it.

**Why:** it is a three-hop chain across two services, described but not verified. Note `errand/model_metadata.py` already downloads `model_prices_and_context_window.json` and reads only two fields — if that file carries window data for the relevant models, part of this may already be sitting unused in the codebase, and the chain may not be needed at all. Check that first; it is the cheapest hop.

### 3. Treat "keep it global" as a live outcome

**Chosen:** frame the per-model question as genuinely open rather than as a foregone conclusion needing justification.

**Why:** a global ceiling has a property a resolved one loses — it is predictable. Every task compacts at the same point regardless of routing, which makes behaviour comparable across models and makes the peak-context series from `context-usage-observability` interpretable without a per-row denominator. A resolved ceiling is more correct per model and less legible in aggregate. Which matters more is exactly what the investigation should decide, and it should be allowed to decide in favour of the status quo.

### 4. The spec is provisional and may not be created

**Chosen:** carry `model-context-window-resolution` as a provisional capability. If the conclusion is that the ceiling stays hand-set and global, no spec is created and this change lands as a decision record.

**Why:** OpenSpec requires a delta to validate, which creates pressure to specify something regardless of what the research finds. Naming the provisional status up front is what stops the process from deciding the outcome.

## Risks / Trade-offs

- **The investigation produces artifacts the conclusion invalidates** → Accepted and expected. The spec exists so the change validates; if the research says "keep it global", the spec is discarded rather than implemented, and that is a successful outcome, not wasted work.
- **Latency data is confounded** → Model, output length, hardware contention, and queueing all sit inside `duration_ms`. Segment by model before drawing a curve, and treat cross-model comparison as unavailable rather than noisy.
- **Measuring before `context-accounting-correctness` lands gives the wrong baseline** → That change alters when compaction fires, which changes the context lengths that appear in the data. Sequence this after it, or the curve describes a system that no longer exists.
- **A resolved per-model ceiling makes stored peaks harder to interpret** → Interacts directly with `context-usage-observability`, which stores the ceiling alongside the peak partly to survive this change. Confirm that decision still holds if the ceiling becomes resolved rather than configured.
- **The 260,352 figure is one model on one host** → Do not generalise from it. Establish the window for each model actually in use before concluding the ceiling is broadly too low.

## Migration Plan

None unless the conclusion requires code. If it does, the migration is whatever that decision implies and belongs in a follow-up change with its own artifacts rather than being appended here.

## Open Questions

These are the investigation, not gaps in it.

- What is the latency cost per 10k tokens of context, per model in use?
- Is there a knee in the curve, and does it fall near 150,000?
- Do the relevant models appear in `model_prices_and_context_window.json` with usable window data, making the LiteLLM/LM Studio chain unnecessary?
- If the ceiling becomes per-model, what governs a task whose model changes mid-run — retry, or a profile that resolves differently?
- Should the ceiling be a fraction of the resolved window rather than an absolute number, so it tracks the model without a per-model setting?
