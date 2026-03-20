## Purpose

Error classification, retry logic for transient LLM API failures, and structured error event emission in the task-runner agent loop.

## Requirements

### Requirement: LLM API error classification

The task-runner SHALL classify exceptions from `Runner.run_streamed()` and its streaming iteration into error categories. Transient errors SHALL include `APIConnectionError`, `APITimeoutError`, `RateLimitError`, and HTTP status codes 429, 502, 503, 504. Non-retryable errors SHALL include `BadRequestError` (400), `AuthenticationError` (401), and any error whose message indicates conversation history corruption (e.g. "Unable to convert openai tool calls"). All other errors SHALL be classified as unknown. The classification function SHALL accept an exception and return one of: `"transient"`, `"non_retryable"`, or `"unknown"`.

#### Scenario: Rate limit error classified as transient

- **WHEN** the LLM API returns a `RateLimitError` (HTTP 429)
- **THEN** the error is classified as `"transient"`

#### Scenario: Connection timeout classified as transient

- **WHEN** the LLM API raises an `APITimeoutError`
- **THEN** the error is classified as `"transient"`

#### Scenario: Bad request classified as non-retryable

- **WHEN** the LLM API returns a `BadRequestError` (HTTP 400)
- **THEN** the error is classified as `"non_retryable"`

#### Scenario: LiteLLM tool conversion error classified as non-retryable

- **WHEN** the LLM API returns HTTP 500 with a message containing "Unable to convert openai tool calls"
- **THEN** the error is classified as `"non_retryable"`

#### Scenario: Unexpected error classified as unknown

- **WHEN** the agent loop raises a `KeyError` or other non-API exception
- **THEN** the error is classified as `"unknown"`

### Requirement: In-process retry for transient LLM errors

The task-runner SHALL retry the agent execution loop when a transient error occurs. The retry SHALL use exponential backoff starting at 2 seconds with a maximum of 3 total attempts (1 initial + 2 retries, delays: 2s, 4s). Each retry SHALL restart `Runner.run_streamed()` from the original user prompt (fresh conversation). If all attempts are exhausted, the task-runner SHALL exit with code 1 as today. The retry count and delay SHALL be logged at INFO level for each attempt.

#### Scenario: Transient error retried successfully

- **WHEN** the first agent execution attempt fails with a `RateLimitError` and the second attempt succeeds
- **THEN** the task completes successfully after one retry, with the retry logged

#### Scenario: All retries exhausted

- **WHEN** all 3 retry attempts fail with transient errors
- **THEN** the task-runner emits an error event and exits with code 1

#### Scenario: Non-retryable error not retried

- **WHEN** the agent execution fails with a `BadRequestError`
- **THEN** the task-runner exits immediately with code 1 without retrying

### Requirement: Structured error event emission

The task-runner SHALL emit error events with additional classification fields. The error event format SHALL be `{"type": "error", "data": {"message": "<error text>", "error_type": "<transient|non_retryable|unknown>", "error_class": "<exception class name>"}}`. The `message` field SHALL contain the string representation of the exception. The `error_type` field SHALL contain the classification result. The `error_class` field SHALL contain the exception's class name (e.g. `"RateLimitError"`, `"APIConnectionError"`).

#### Scenario: Error event includes classification

- **WHEN** the agent execution fails with an `APIConnectionError` after all retries
- **THEN** the emitted error event includes `"error_type": "transient"` and `"error_class": "APIConnectionError"`

#### Scenario: Error event backward compatible

- **WHEN** the task-runner emits an error event
- **THEN** the event includes a `message` field containing the error text, preserving the existing format

### Requirement: Malformed tool call sanitization in model input filter

The `_sanitize_tool_calls` function SHALL scan input items in Responses API format. It SHALL iterate the input list looking for dict items with `"type": "function_call"` and validate the `"arguments"` field as parseable JSON. When invalid JSON arguments are detected, the function SHALL attempt to repair the JSON using the existing `_repair_truncated_json` helper. If repair succeeds, the repaired arguments SHALL replace the original. If repair fails, the arguments SHALL be replaced with a JSON object containing an error placeholder: `{"error": "malformed_arguments", "original_fragment": "<first 200 chars>"}`. The function SHALL log a warning for each sanitized tool call.

#### Scenario: Valid function_call items pass through unchanged

- **WHEN** the input contains a `{"type": "function_call", "arguments": "{\"path\": \"/file.md\", \"content\": \"hello\"}"}` item
- **THEN** the item is returned unchanged

#### Scenario: Truncated function_call arguments are repaired

- **WHEN** the input contains a `{"type": "function_call", "arguments": "{\"path\": \"/file.md\""}` item (unclosed brace)
- **THEN** the arguments are repaired to `{"path": "/file.md"}` and a warning is logged

#### Scenario: Unrepairable function_call arguments get error placeholder

- **WHEN** the input contains a `{"type": "function_call"}` item with arguments that cannot be repaired to valid JSON
- **THEN** the arguments are replaced with `{"error": "malformed_arguments", "original_fragment": "..."}` and a warning is logged

#### Scenario: Non-function_call items are ignored

- **WHEN** the input contains items with types other than `"function_call"` (e.g. `"message"`, `"function_call_output"`)
- **THEN** those items are not modified by the sanitization

### Requirement: Truncation-aware error message injection

When the sanitization filter detects and repairs a malformed `function_call` item, it SHALL search the remaining input items for a corresponding `function_call_output` item with a matching `call_id`. If found, the filter SHALL replace the output text with a truncation recovery message. The message SHALL state that the tool call arguments were truncated due to output token limits, the tool call failed, and the LLM should retry by splitting large content into multiple smaller tool calls. The original tool output text SHALL be preserved in the replacement message for context.

#### Scenario: Truncation error message injected into matching tool output

- **WHEN** a `function_call` item with `call_id` "abc123" has malformed arguments AND a `function_call_output` item with `call_id` "abc123" exists
- **THEN** the `function_call_output` item's output is replaced with a message containing: the word "truncated", guidance to split into smaller calls, and the original error text

#### Scenario: No matching tool output — sanitization only

- **WHEN** a `function_call` item has malformed arguments but no corresponding `function_call_output` item exists in the input
- **THEN** the arguments are repaired/replaced but no output item is modified

#### Scenario: Multiple truncated tool calls handled independently

- **WHEN** the input contains two `function_call` items with malformed arguments, each with different `call_id` values
- **THEN** each is repaired independently and each matching `function_call_output` receives the truncation error message

### Requirement: Empty response error event emission

When the agent loop completes without exception but produces empty output, the task-runner SHALL emit a structured error event. The event format SHALL be `{"type": "error", "data": {"message": "LLM returned empty response", "error_type": "empty_response", "error_class": "EmptyResponseError"}}`. This event SHALL be emitted via the existing `emit_event()` mechanism to stderr, consistent with the error event format defined in the structured error event emission requirement.

#### Scenario: Error event emitted for empty response

- **WHEN** the agent loop completes and `result.final_output` is empty
- **THEN** an error event is emitted to stderr with `"type": "error"`, `"error_type": "empty_response"`, and `"error_class": "EmptyResponseError"`

#### Scenario: Error event format matches existing error events

- **WHEN** an empty response error event is emitted
- **THEN** the event JSON contains the same fields as other error events: `message`, `error_type`, and `error_class`
