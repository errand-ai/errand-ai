## Why

Once `fix-context-compaction` made compaction work, production logs immediately showed it working *repeatedly* — four compactions in 104 seconds on one task, each re-summarising the same messages:

```
11:31:02 triggered: ~153,938 tokens, 53 messages
11:31:30 complete:  53 → 5 messages,  ~153,938 → ~16,100   (49 summarised)
11:32:01 triggered: ~157,402 tokens, 57 messages
11:32:01 complete:  57 → 9 messages,  ~157,402 → ~19,564   (49 summarised)
11:32:10 triggered: ~158,648 tokens, 61 messages
11:32:10 complete:  61 → 13 messages, ~158,648 → ~20,809   (49 summarised)
11:32:16 triggered: ~172,462 tokens, 65 messages
11:32:46 complete:  65 → 13 messages, ~172,462 → ~19,615   (53 summarised)
```

The input grows (53 → 65 messages) while the same oldest 49 are summarised over and over. Real calls took **28s and 30s**; the ~24ms ones are LiteLLM cache hits on a near-identical prompt and will stop helping once content shifts. Over a long task this is O(n²) summarisation cost.

Research into the SDK and into how other agent systems handle this produced four conclusions, one of which is a previously-unknown bug.

## What the research established

### 1. The SDK will not solve this, and it is not a misuse

`call_model_input_filter` is documented for exactly our use — *"edit the input sent to the model e.g. to stay within a token limit"* — but is per-call by construction. Verified in source: after each turn the loop rebuilds history from its own items (`streamed_result._model_input_items = turn_result.pre_step_items + turn_result.new_step_items`), and the filter's output is never written back. The SDK's own internal design note states it: *"The next model input may be filtered, but session history needs the full unfiltered item sequence."*

Sessions do not help either. `prepare_input_with_session` is called **once, before the turn loop**; `save_result_to_session` writes per turn but the in-flight run never re-reads. So a mid-run session rewrite changes what is *stored*, not what the current run sends. `OpenAIResponsesCompactionSession` is Responses-API only and rejects non-OpenAI models, so it is closed to us on LiteLLM.

Maintainers have declined to build a provider-agnostic equivalent (`seratch`, issue #2244: *"We don't plan to have the proposed module as part of this core SDK… please build the module as your own package or library"*), and the still-open issue #2671 acknowledges the gap directly: *"this SDK does not yet support the pattern."*

### 2. Our design is mainstream — the shape needs no change

"Trigger at a token threshold, keep recent N, LLM-summarise the older portion into a structured checkpoint, fall back to dropping oldest on failure" is near-identical to Cline's shipped implementation and structurally matches Codex, OpenHands, LangChain and Anthropic's own API.

`KEEP_RECENT_TOKENS = 20_000` is, remarkably, the convergent constant: Cline's `DEFAULT_PRESERVE_RECENT_TOKENS = 20_000` and Codex's `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000`. **This closes follow-up 7.3 from `fix-context-compaction`** — the value needs no revisiting. Our 13% retention against a 150k budget is a consequence of the larger budget, not aggression, and the one measured study found less retention performed *better*.

### 3. The fix for recomputation is chaining, not caching — and we already have the code for it

The community answer is **incremental summarisation**: feed the previous summary into the next one and summarise only what is new since it. Cline's `findLatestSummaryIndex()` extracts the prior summary and threads it in; LangMem describes caching running summaries as *"what allows `summarize_messages` to avoid re-summarizing the same messages on every conversation turn"*.

errand already implements this. `MERGE_COMPACTION_PROMPT` and `_is_compaction_summary()` exist for exactly this purpose — and they are **dead code**, because the merge path detects a prior summary by looking for `COMPACTION_SUMMARY_PREFIX` *in the messages*, and the compacted list never persists into the SDK's history. Every compaction therefore takes the first-compaction path.

The fix is to hold the previous summary in our own module-level state — alongside the backoff state added in `fix-context-compaction`, with the same per-attempt reset — rather than trying to read it back out of a history the SDK owns. That makes the existing merge path reachable and turns O(n²) into O(n).

### 4. NEW BUG: the compaction split can orphan a tool call from its result

The split point is chosen purely by accumulating tokens backwards until `KEEP_RECENT_TOKENS`, with no check for tool-call pairing:

```python
for i in range(len(messages) - 1, -1, -1):
    ...
    split_idx = i + 1
to_summarize, to_keep = messages[:split_idx], messages[split_idx:]
```

If the boundary lands between a `function_call` and its `function_call_output`, the kept history begins with an orphaned output whose call was summarised away — a provider error that fires precisely when context is already under pressure. `_sanitize_tool_calls` does not cover this; it repairs malformed JSON arguments and runs before compaction.

Cline, OpenHands, LangChain and strix all snap the cut point to a boundary with no tool call left open. We do not. This was not previously known and is the most urgent item here.

## What Changes

- **Snap the compaction split to a safe boundary** — never between a `function_call` and its matching `function_call_output`.
- **Chain summaries.** Keep the previous summary and the index it covered in module-level state; summarise only messages added since, and merge via the existing `MERGE_COMPACTION_PROMPT`. Reset per agent attempt, like the backoff state.
- **Log when a compaction is a merge rather than a full re-summarisation**, so the saving is observable rather than inferred from timing.

**Not in scope, deliberately:**

- Changing `KEEP_RECENT_TOKENS` — settled by the research above.
- The overflow-retry architecture used by strix, koder and Datus (compact between runs, restart `Runner` with the compacted history). It is the only approach that makes compaction genuinely persist, and errand is closer to it than expected since it already retries around `Runner.run_streamed()`. But it is a restructuring of the runner's control flow and wants its own change.
- Evicting large reconstructible tool outputs before summarising — the tiered "compact then summarise" pattern, and `agents.extensions.ToolOutputTrimmer` (undocumented but provider-agnostic, targets exactly our 128k/116k/94k file reads). Likely higher value than anything here, and also its own change.
- **Constraint pinning.** See below — a safety concern, not an efficiency one, and it should not be buried in this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-runner-context-compaction`: split-point safety; chained summarisation making the existing merge path reachable; a distinguishable log line for merge-vs-full compaction.

## Impact

- **Code**: `task-runner/main.py` — `_compact_context` split selection, plus summary state alongside `_compaction_backoff`.
- **Correctness risk**: chaining means a wrong summary silently misrepresents history rather than failing loudly. The state must record exactly which messages a summary covers, and be reset on the same per-attempt boundary as the backoff state — a stale summary spliced in front of unrelated messages is worse than recomputing.
- **The dead merge path becomes live for the first time.** `MERGE_COMPACTION_PROMPT` has never executed in production, so it is unproven code being switched on. It needs testing as new, not as existing.
- **Measurement**: the WARNING-level lifecycle logs from `fix-context-compaction` are how this is confirmed — compare compaction call counts per task before and after.

### Flagged separately: compaction erases safety constraints

[Governance Decay](https://arxiv.org/abs/2606.22528) benchmarks 1,323 episodes: prohibited-action rate **0% with the policy in context, 30% average after compaction**, 59% for the worst model. Conditioned on the summary, it is 0% when constraints survived and 38% when they were dropped. The paper also demonstrates a Compaction-Eviction Attack — content crafted to bias the summariser into omitting policies.

errand is more exposed than a chat product: tasks run unattended with real side effects (Slack posts, Google Workspace writes, email), and system-skill instructions, profile constraints and tool restrictions currently sit *inside* the compactable region. This deserves its own change — pinning those outside the compactable region or re-injecting them post-compaction — and is recorded here only so it is not lost.
