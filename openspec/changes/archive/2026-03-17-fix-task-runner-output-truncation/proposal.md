## Why

The task-runner agent fails catastrophically when the LLM generates a tool call whose arguments exceed the output token limit. The LLM truncates mid-JSON (e.g. a `gdrive_write_file` call with a large `content` argument), producing invalid JSON arguments. This causes two cascading failures: (1) the MCP tool rejects the malformed arguments, and (2) on the next LLM turn, LiteLLM crashes with HTTP 500 trying to serialize the truncated tool call for Bedrock's Converse API. The existing `_sanitize_tool_calls` filter (PR #88) scans for chat completion message format (`{"role": "assistant", "tool_calls": [...]}`) but the Agents SDK passes Responses API item format (`{"type": "function_call", "arguments": "..."}`), so the filter never matches and is effectively a no-op. Additionally, no `max_tokens` is set on the model, so Bedrock applies its own conservative default (~4096 tokens), making truncation likely for any substantial tool call output.

## What Changes

- Add a model-aware max output tokens lookup table that maps model name patterns to their maximum supported output tokens, and set `max_tokens` on `ModelSettings` at startup to give the LLM the best chance of completing its output
- Fix `_sanitize_tool_calls` to scan the correct item format (Responses API `function_call` items) instead of chat completion messages
- Detect truncated tool call arguments and inject a clear, actionable error message into the tool result telling the LLM its output was truncated and it should split large content into multiple smaller tool calls
- Allow `MAX_OUTPUT_TOKENS` env var to override the lookup table value

## Capabilities

### New Capabilities
- `task-runner-output-token-limits`: Model-aware max output token resolution and configuration for the task-runner agent

### Modified Capabilities
- `task-runner-error-resilience`: The input sanitization filter must handle Responses API item format and detect/recover from truncated tool call arguments

## Impact

- **Code**: `task-runner/main.py` — model settings, `_sanitize_tool_calls`, `filter_model_input`
- **Config**: New optional env var `MAX_OUTPUT_TOKENS`
- **Tests**: `task-runner/test_main.py` — new tests for token lookup, truncation detection, item format sanitization
- **Dependencies**: None — uses existing Agents SDK and LiteLLM capabilities
- **Breaking changes**: None — existing behavior is preserved, new behavior is additive
