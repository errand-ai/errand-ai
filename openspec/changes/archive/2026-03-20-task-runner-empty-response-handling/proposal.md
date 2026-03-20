## Why

The task-runner silently reports success when the LLM returns an empty response (HTTP 200 with no text content). This was observed in production when a `glm-4.7-flash` model's output was misclassified as `reasoning_content` by LiteLLM, leaving `message.content` empty and `tool_calls` null. The task completed with `{"status": "completed", "result": ""}` — indistinguishable from a successful run to the backend and user. Empty responses should be treated as failures so the backend can report the issue and the task can be retried.

## What Changes

- Detect empty `final_output` from the agent loop and treat it as a failure instead of a successful completion
- Emit a structured error event when empty response is detected
- Exit with non-zero code so the backend marks the task as failed
- Add tests covering the empty response detection

## Capabilities

### New Capabilities

_None — this is a behavioral fix within existing capabilities._

### Modified Capabilities

- `task-runner-agent`: Add validation that final output is non-empty before reporting success
- `task-runner-error-resilience`: Add empty-response as a classified failure mode with structured error event

## Impact

- `task-runner/main.py`: Output validation logic after the agent loop (lines ~725-748)
- `task-runner/test_main.py`: New test cases for empty response handling
- Backend behavior: Tasks that previously completed with empty results will now be reported as failed, allowing retry or user notification
