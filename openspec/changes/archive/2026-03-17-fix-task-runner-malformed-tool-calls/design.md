## Context

The task-runner uses the OpenAI Agents SDK with LiteLLM as an OpenAI-compatible proxy to Bedrock. The agent loop in `main.py` runs `Runner.run_streamed()` and iterates streaming events. A `filter_model_input` function (registered via `RunConfig.call_model_input_filter`) already intercepts conversation history before each LLM call for screenshot stripping and context trimming.

When an LLM generates a tool call with truncated/malformed JSON arguments, this corrupted tool call becomes part of the conversation history. On the next turn, LiteLLM attempts to convert the full history to Bedrock's Converse format, which requires `json.loads()` on tool call arguments. The malformed JSON causes a 500 error that persists across retries because the poisoned message is always present.

Currently, the only error handling is a catch-all `except Exception: sys.exit(1)` at the end of the agent loop.

## Goals / Non-Goals

**Goals:**
- Sanitize malformed tool call arguments in conversation history before they reach LiteLLM
- Classify LLM API errors as transient vs non-retryable and handle each appropriately
- Allow the agent to self-heal from malformed tool calls by continuing the conversation with an error indication

**Non-Goals:**
- Fixing the root cause in LiteLLM's Bedrock conversion (upstream issue)
- Implementing general-purpose JSON repair beyond simple truncation cases
- Adding retry logic at the TaskManager level (already exists with up to 3 retries)
- Handling non-LLM errors (MCP failures, filesystem errors, etc.) — these already work fine

## Decisions

### 1. Sanitize tool call arguments in `filter_model_input`

**Decision**: Add a `_sanitize_tool_calls` step to the existing `filter_model_input` chain, running before screenshot stripping and context trimming.

**Rationale**: The `call_model_input_filter` is the only interception point between the SDK's conversation history and the LLM API call. By sanitizing here, we fix the history before LiteLLM sees it, preventing the 500 entirely. This is more reliable than catching the error after the fact, because once the SDK gets a 500, the conversation state may be inconsistent.

**Alternatives considered**:
- *Catch the 500 and strip the offending message*: Fragile — requires parsing LiteLLM error messages to identify which tool call is malformed, and the SDK may not expose enough state to safely modify the conversation mid-run.
- *Use a custom model class that wraps the API call*: Overengineered — the filter hook already exists for exactly this purpose.

**Approach**:
- Scan assistant messages for `tool_calls` entries (OpenAI format: `{"type": "function", "function": {"name": "...", "arguments": "..."}}`)
- For each tool call, attempt `json.loads(arguments)`
- If it fails, attempt repair: close unclosed strings, brackets, braces
- If repair succeeds, replace arguments with the repaired JSON
- If repair fails, replace the arguments with `{"error": "malformed_arguments", "original_fragment": "<first 200 chars>"}` — this is valid JSON that LiteLLM can serialize, and the agent will see the tool result as a failure it can reason about
- Log every sanitization for observability

### 2. Repair strategy for truncated JSON

**Decision**: Use a simple sequential repair approach — no external dependencies.

**Approach** (in order):
1. Try `json.loads()` — if it works, no repair needed
2. Close any unclosed string literal (find unmatched `"`)
3. Close unclosed brackets/braces by tracking the open stack
4. Try `json.loads()` again on the repaired string
5. If still invalid, fall back to the error placeholder

**Rationale**: The observed failure mode is truncation (missing closing braces/brackets). A stack-based closer handles this well. We deliberately avoid complex heuristics or third-party JSON repair libraries — the goal is to handle the common case (truncated output), not every possible malformation.

### 3. Error classification and retry in the agent loop

**Decision**: Wrap the streaming event loop in error handling that distinguishes transient from non-retryable errors, with limited in-process retries for transient failures.

**Error categories**:
- **Transient** (retry with exponential backoff): `APIConnectionError`, `APITimeoutError`, `RateLimitError`, HTTP 429, HTTP 502/503/504
- **Non-retryable** (fail immediately): `BadRequestError` (400), `AuthenticationError` (401), HTTP 500 with conversation-history-related error messages
- **Unknown** (fail immediately): anything else

**Retry parameters**: Max 3 total attempts (1 initial + 2 retries), exponential backoff starting at 2 seconds (2s, 4s). These are retries of the entire `Runner.run_streamed()` call (restarting the agent turn), not individual API calls — the OpenAI SDK already retries individual HTTP requests internally.

**Rationale**: The OpenAI SDK's built-in retries handle transient HTTP failures for individual requests, but don't restart the agent loop when a streaming iteration fails. A lightweight retry around the outer loop covers cases where the SDK gives up but the error is still transient.

### 4. Structured error events

**Decision**: Extend the error event format to include `error_type` (transient/non-retryable/unknown) and `error_class` (the exception class name).

**Current format**: `{"type": "error", "data": {"message": "..."}}`
**New format**: `{"type": "error", "data": {"message": "...", "error_type": "transient|non_retryable|unknown", "error_class": "APIConnectionError"}}`

This is backward-compatible — the `message` field is unchanged, new fields are additive.

## Risks / Trade-offs

- **JSON repair may produce semantically wrong but syntactically valid JSON** → Mitigation: The agent will see the tool result (which will likely be an error from the MCP server due to missing arguments) and can retry with correct arguments. The repair only needs to prevent the LiteLLM 500, not produce correct tool arguments.
- **Restarting `Runner.run_streamed()` on transient errors loses the current conversation state** → Mitigation: This is already the behavior today (task retries start from scratch). In-process retries are an improvement over full task restarts because they're faster and don't consume retry budget at the TaskManager level.
- **Filter adds latency to every LLM call** → Mitigation: The JSON parse check is negligible compared to LLM latency. Only malformed calls trigger repair logic.
