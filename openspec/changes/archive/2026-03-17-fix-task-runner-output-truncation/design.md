## Context

The task-runner uses the OpenAI Agents SDK with `Runner.run_streamed()` and a `call_model_input_filter` callback to sanitize messages before each LLM call. The LLM is accessed via a LiteLLM proxy that translates OpenAI chat completion requests to provider-specific formats (e.g. Bedrock Converse API). When the LLM generates tool call arguments that exceed the output token limit, the response is truncated mid-JSON. The existing sanitization filter (`_sanitize_tool_calls`) was built for chat completion message format but the Agents SDK passes Responses API input items — a completely different schema.

Key constraint: the `call_model_input_filter` receives `list[TResponseInputItem]` where each item is a dict with `{"type": "function_call", "arguments": "...", ...}` — NOT `{"role": "assistant", "tool_calls": [...]}`.

## Goals / Non-Goals

**Goals:**
- Set model-appropriate `max_tokens` to minimize truncation occurrences
- Detect truncated tool call arguments and repair the JSON so LiteLLM can serialize the history
- Give the LLM clear, actionable feedback about truncation so it can self-correct (split into smaller chunks)
- Make the token limit configurable via env var for deployment flexibility

**Non-Goals:**
- Modifying the Agents SDK or LiteLLM source code
- Detecting truncation at the streaming level (would require SDK changes to surface `finish_reason`)
- Preventing all possible truncation — even with high max_tokens, content can exceed limits
- Changing how the MCP tools themselves handle malformed arguments

## Decisions

### Decision 1: Pattern-based model lookup table for max output tokens

Use substring pattern matching against the model name to resolve max output tokens. Patterns are checked in order (most specific first). This avoids exact model ID enumeration and works regardless of provider prefix (e.g. `bedrock/`, `vertex/`).

```python
_MAX_OUTPUT_TOKENS_PATTERNS = [
    ("opus-4-6",      128000),
    ("opus-4-5",       64000),
    ("opus-4-1",       32000),
    ("opus-4",         32000),
    ("sonnet-4",       64000),  # catches 4, 4-5, 4-6
    ("haiku-4",        64000),  # catches 4-5
    ("claude-3",        4096),
    ("gpt-4.1",        32768),
    ("gpt-4o",         16384),
    ("gpt-5",         100000),
    ("gemini-2.5",     65535),
    ("gemini-2",       65535),
]
DEFAULT_MAX_OUTPUT_TOKENS = 16384
```

**Rationale**: A static table is zero-cost at runtime, has no network dependency, and is trivially testable. The pattern approach handles model name variations across providers. The default of 16,384 is safe for all current models and represents a significant improvement over the implicit provider default (~4096).

### Decision 2: Scan Responses API item format in sanitization filter

Rewrite `_sanitize_tool_calls` to scan for `{"type": "function_call"}` items in the input list and validate their `arguments` field as JSON. This matches the actual data format the Agents SDK passes to the `call_model_input_filter`.

**Rationale**: The current filter checks `isinstance(msg, dict) and msg.get("role") == "assistant"` which never matches Responses API items. The fix must match the correct schema.

### Decision 3: Repair truncated JSON AND enhance the tool result error message

When a malformed `function_call` item is detected:
1. **Repair the arguments JSON** using the existing `_repair_truncated_json` helper (close unclosed strings/brackets) — this prevents LiteLLM from crashing with HTTP 500 on the next turn
2. **Find the corresponding `function_call_output` item** (matching `call_id`) and replace its output text with a specific truncation recovery message that instructs the LLM to split large content into multiple smaller tool calls

**Rationale**: Both steps are necessary. Repairing JSON prevents the cascading LiteLLM failure. Enhancing the error message turns a cryptic MCP parse error into actionable guidance that teaches the LLM to self-correct. The MCP server's generic "An error occurred while parsing tool arguments" doesn't tell the LLM *why* or *how to fix it*.

### Decision 4: Env var override with MAX_OUTPUT_TOKENS

Allow `MAX_OUTPUT_TOKENS` env var to override the lookup table value. If set, it takes precedence over the pattern-based resolution.

**Rationale**: Deployment flexibility — operators may know their specific model's limits or want to constrain output for cost reasons.

## Risks / Trade-offs

- **Risk**: The lookup table can become stale as new models are released. **Mitigation**: The default fallback of 16,384 is safe, and the env var override handles edge cases. Table updates are low-effort.
- **Risk**: Setting max_tokens too high could cause Bedrock validation errors if `prompt_tokens + max_tokens > context_window`. **Mitigation**: This is a provider-side validation that returns a clear error; the retry logic handles it. In practice, context windows are 200k+ and max_tokens of 64k-128k is well within bounds.
- **Trade-off**: Repairing truncated JSON gives the LLM a "valid but wrong" tool call in history (missing content). This is acceptable because the enhanced error message clearly explains what happened, and the alternative (leaving invalid JSON) crashes the entire agent.
