## Why

The task runner's current context management (`_trim_context_window`) drops the oldest messages when the conversation exceeds the token budget. This silently loses goals, decisions, progress, and file context — causing quality degradation on long, complex tasks where the agent forgets what it was doing, re-reads files it already read, or revisits decisions it already made. Pi's coding agent demonstrates that LLM-summarized compaction (asking the LLM to produce a structured checkpoint summary before trimming) preserves critical context across the entire task lifecycle.

## What Changes

- Replace `_trim_context_window()` with `_compact_context()` that uses a summarization LLM call to produce a structured checkpoint before dropping old messages
- Add a summarization prompt that produces: Goal, Progress (done/in-progress/blocked), Key Decisions, Next Steps, and Files (read/modified)
- Support subsequent compactions by merging new information into the existing summary rather than re-summarizing from scratch
- Track file read/modification operations across compactions by scanning tool call messages
- Keep the existing `_strip_screenshots` and `_sanitize_tool_calls` filters unchanged

## Capabilities

### New Capabilities
- `task-runner-context-compaction`: LLM-summarized context compaction for the task runner agent loop

### Modified Capabilities

## Impact

- `task-runner/main.py` — replace `_trim_context_window` with compaction logic, add summarization prompts and helpers
- No new dependencies — uses the existing OpenAI client already available in the task runner
- No database changes
- No API changes
- Minor increase in LLM token usage per compaction (~1k output tokens for the summary)
