## Context

The task runner (`task-runner/main.py`) uses the OpenAI Agents SDK's `Runner.run_streamed()` to execute tasks. A `call_model_input_filter` hook processes messages before each LLM call, applying three filters in order: `_sanitize_tool_calls`, `_strip_screenshots`, `_trim_context_window`. The current `_trim_context_window` drops oldest messages (except the first user prompt) until estimated tokens are under `MAX_CONTEXT_TOKENS` (default 150k). This loses context silently.

The filter hook is synchronous (not async). The task runner already uses synchronous `subprocess.run` for `execute_command`, so blocking the event loop briefly for a summarization call is consistent with existing patterns.

## Goals / Non-Goals

**Goals:**
- Replace naive message dropping with LLM-summarized compaction
- Produce structured checkpoint summaries preserving goals, progress, decisions, and file context
- Support iterative compaction (merging new context into an existing summary)
- Track which files the agent has read and modified across compactions

**Non-Goals:**
- Session branching or tree-based conversation navigation (Pi feature, not relevant to headless execution)
- Split-turn handling (Pi handles mid-turn cuts — we keep the split point at message boundaries for simplicity)
- Changing the OpenAI Agents SDK or the streaming architecture
- Changing `_sanitize_tool_calls` or `_strip_screenshots`

## Decisions

### 1. Synchronous summarization inside `filter_model_input`

Make the summarization LLM call directly inside the filter using the synchronous OpenAI client (`openai.OpenAI`, not `AsyncOpenAI`). The filter is called synchronously by the Agents SDK before each model invocation.

**Rationale:** Simplest approach. The task runner already blocks the event loop in `execute_command` via `subprocess.run`. A summarization call produces ~500-1k tokens of output and completes in 2-5 seconds. Async alternatives (e.g., between-turn hooks with shared state) add complexity for minimal benefit in a headless task runner.

**Alternative considered:** Proactive summarization in `StreamEventEmitter.on_agent_end()` with shared state passed to the filter. Rejected because it introduces coupling between the hooks and the filter, and the timing is fragile (what if tokens spike from a single large tool result between on_agent_end and the next filter call?).

### 2. Two-prompt approach: initial summary vs. merge update

First compaction uses a "create summary" prompt. Subsequent compactions use a "merge into existing summary" prompt that preserves prior context and adds new information.

**Rationale:** Matches Pi's approach and avoids the summary growing stale or losing older context. The merge prompt explicitly instructs the LLM to preserve existing information, update progress, and remove only clearly irrelevant items.

### 3. Summary injected as the first user message

The compacted summary replaces the original first message and all dropped messages, formatted as:

```
The conversation history before this point was compacted into the following summary:

<summary>
[structured summary + file lists]
</summary>
```

**Rationale:** The LLM needs to see the summary as context. A user-role message at position 0 is consistent with how the original user prompt sits at position 0 today. The system prompt (`instructions`) is separate and unaffected.

### 4. Keep ~20k tokens of recent messages

When compacting, keep approximately 20,000 tokens (estimated) of the most recent messages. Summarize everything before that point.

**Rationale:** Matches Pi's default `keepRecentTokens: 20000`. Recent messages contain the active working context that the LLM is currently reasoning about — summarizing them would lose precision on in-flight work.

### 5. File tracking via tool call scanning

Scan `execute_command` tool calls in messages being summarized. Use heuristics to classify commands:
- **Read**: `cat`, `head`, `tail`, `less`, `grep` (with file args)
- **Modified**: redirects (`>`, `>>`), `sed -i`, `tee`, `cp`, `mv`, `rm`, `mkdir`, `touch`

Append file lists to the summary as `<read-files>` and `<modified-files>` XML blocks.

**Rationale:** Best-effort tracking given that errand uses a single `execute_command` tool rather than distinct file tools. The heuristics won't catch every case (e.g., Python scripts that write files), but they'll capture the common patterns. The file tools change (if implemented) would make this precise.

### 6. Use a small/fast model for summarization

Use the same model and endpoint configured for the task (`OPENAI_BASE_URL`, `OPENAI_API_KEY`) but request a smaller model if available via a `COMPACTION_MODEL` env var (defaulting to the task's model). This allows routing summarization to a cheaper/faster model.

**Rationale:** Summarization doesn't require the full reasoning capability of the task model. A fast model produces adequate summaries and reduces cost/latency. But defaulting to the task model ensures it works without additional configuration.

## Risks / Trade-offs

- **Summarization quality** — The summary is only as good as the LLM produces. Poor summaries could lose critical context. Mitigation: structured prompt with explicit sections, and the merge approach preserves prior summaries.
- **Latency** — Each compaction adds 2-5 seconds of blocking time. Mitigation: compaction only triggers when context is nearly full, which happens rarely (typically 1-3 times per task).
- **Token cost** — Each compaction costs ~2k input tokens (old messages serialized) + ~1k output tokens (summary). Mitigation: minor compared to the task's total token usage.
- **Sync LLM call in filter** — Blocks the event loop. Mitigation: acceptable for a headless task runner; the existing `execute_command` does the same.

## Open Questions

- Should `COMPACTION_MODEL` default to a specific fast model (e.g., `gpt-4.1-mini`) or always use the task model? Starting with the task model as default is safest.
