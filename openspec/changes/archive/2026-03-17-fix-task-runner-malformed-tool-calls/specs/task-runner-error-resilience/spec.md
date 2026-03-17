## ADDED Requirements

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
