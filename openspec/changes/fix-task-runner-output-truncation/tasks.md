## 1. Max Output Token Resolution

- [x] 1.1 Add `_MAX_OUTPUT_TOKENS_PATTERNS` lookup table and `resolve_max_output_tokens(model: str) -> int` function that matches model name substrings in priority order, with `DEFAULT_MAX_OUTPUT_TOKENS = 16384` fallback
- [x] 1.2 Add `MAX_OUTPUT_TOKENS` env var handling — if set to valid positive integer, override the lookup result; log warning and ignore if invalid
- [x] 1.3 Set `max_tokens` on `ModelSettings` in the agent creation code using the resolved value, and log the resolved value at INFO level at startup

## 2. Fix Sanitization Filter Format

- [x] 2.1 Rewrite `_sanitize_tool_calls` to scan for `{"type": "function_call"}` items (Responses API format) instead of `{"role": "assistant", "tool_calls": [...]}` (chat completion format), validating the `arguments` field as parseable JSON
- [x] 2.2 When malformed arguments are detected, repair using `_repair_truncated_json` or replace with error placeholder `{"error": "malformed_arguments", "original_fragment": "..."}`

## 3. Truncation Recovery Message

- [x] 3.1 After repairing a malformed `function_call` item, search input items for matching `function_call_output` (same `call_id`) and replace its output with a truncation recovery message that instructs the LLM to split content into smaller tool calls
- [x] 3.2 Preserve the original tool output text within the replacement message for context

## 4. Tests

- [x] 4.1 Add tests for `resolve_max_output_tokens` — known models (Claude, GPT, Gemini), unknown models (default), provider-prefixed model names
- [x] 4.2 Add tests for `MAX_OUTPUT_TOKENS` env var override — valid override, invalid value ignored
- [x] 4.3 Add tests for `_sanitize_tool_calls` with Responses API format — valid items pass through, truncated arguments repaired, unrepairable arguments get placeholder
- [x] 4.4 Add tests for truncation recovery message injection — matching `function_call_output` updated, no match leaves items unchanged, multiple truncated calls handled independently
