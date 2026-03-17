## Why

LLMs occasionally generate tool calls with truncated or malformed JSON arguments (e.g. missing closing braces, incomplete strings). When this happens, LiteLLM cannot convert the malformed tool call in the conversation history to Bedrock's Converse API format, returning a 500 error. This 500 is non-retryable because the poisoned tool call is baked into the conversation history — every subsequent LLM call includes it and fails identically. The task-runner currently has no specific error handling for API failures, so the entire task crashes and retries from scratch (up to 3 times), all of which fail the same way if the model reproduces the same truncation pattern.

Observed in production: Claude Sonnet 4.5 called `gdrive_write_file` with arguments `{"path": "/DevOps-Contract-Market-Research-Report.md"` (missing content field and closing brace) when attempting to write a large file. LiteLLM's `json.loads()` on the arguments failed, causing an unrecoverable 500 loop.

## What Changes

- **Sanitize malformed tool calls in `filter_model_input`**: Before each LLM call, scan assistant messages for tool calls with invalid JSON arguments. Attempt to repair truncated JSON (e.g. close unclosed braces/brackets/strings). If repair fails, replace the malformed tool call with a synthetic tool result indicating the call failed due to invalid arguments, so the agent can reason about the failure and retry the tool call with valid arguments.
- **Classify API errors as retryable vs non-retryable**: Replace the catch-all `except Exception: sys.exit(1)` with specific error handling that distinguishes transient errors (rate limits, timeouts, connection errors) from non-retryable errors (malformed conversation history, invalid requests). For transient errors, retry with exponential backoff within the task-runner process before giving up. For non-retryable errors related to conversation history corruption, attempt to strip the offending messages and continue the agent loop.
- **Emit structured error context**: When the task-runner does fail, include error classification (transient vs non-retryable) and the error type in the emitted error event, improving observability.

## Capabilities

### New Capabilities

- `task-runner-error-resilience`: Error classification, retry logic for transient LLM API failures, and conversation history sanitization for malformed tool calls in the task-runner agent loop.

### Modified Capabilities

- `agent-context-management`: The `filter_model_input` function gains a new responsibility — sanitizing malformed tool call arguments in addition to its existing screenshot stripping and context trimming duties.

## Impact

- **Code**: `task-runner/main.py` — `filter_model_input`, the main agent loop error handling, and the `StreamEventEmitter`
- **Tests**: `task-runner/test_main.py` — new tests for malformed tool call sanitization and error classification
- **Dependencies**: No new dependencies (JSON repair uses stdlib)
- **Behavior**: Tasks that previously crashed on malformed tool calls will now self-heal by sanitizing conversation history and allowing the agent to retry the tool call. Transient API errors will be retried in-process rather than requiring full task restarts.
