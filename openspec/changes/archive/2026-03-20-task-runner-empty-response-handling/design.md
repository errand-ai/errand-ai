## Context

The task-runner agent loop (`main.py`) extracts `result.final_output` from the openai-agents SDK after `Runner.run_streamed()` completes. When `final_output` is empty or None, the current code wraps it as `{"status": "completed", "result": ""}` and exits with code 0. The backend receives this as a successful task completion with no output.

This was observed in production when a model's response content was misrouted (e.g., output classified as `reasoning_content` instead of `content` by LiteLLM, or tool calls lost due to endpoint mismatch). The HTTP request succeeded (200), the agent loop completed without exceptions, but the final output was an empty string.

The existing `task-runner-error-resilience` spec handles API exceptions (retries, error classification) but does not cover the case where the API call succeeds with empty content.

## Goals / Non-Goals

**Goals:**
- Detect empty final output after the agent loop and treat it as a failure
- Emit a structured error event so the failure is visible in logs and telemetry
- Exit with non-zero code so the backend marks the task as failed (enabling retry or user notification)

**Non-Goals:**
- Retry the agent loop on empty response (this could be added later but is out of scope — the root cause is typically a model/config issue, not a transient failure)
- Diagnose why the response was empty (that's a LiteLLM/model concern, not a task-runner concern)
- Change the structured output schema (`TaskRunnerOutput`)

## Decisions

### Empty response detection point

**Decision**: Validate after `result.final_output` extraction, before any output formatting.

**Rationale**: The check sits at `main.py:726-727` where `final_output` is first accessed. This is the earliest point where we know the agent loop completed without exception but produced no output. Checking here catches all empty-output scenarios regardless of cause (empty `message.content`, missing tool calls, etc.).

**Alternative considered**: Checking inside the streaming event loop — rejected because the agent may legitimately produce no text events mid-stream if it's only doing tool calls. The final output is the right place to validate.

### Failure reporting mechanism

**Decision**: Emit a structured error event via `emit_event()`, report a `"failed"` status via the callback/output, and exit with code 1.

**Rationale**: This aligns with the existing error-handling pattern in the retry loop (from `task-runner-error-resilience`). The backend already handles non-zero exit codes as task failures. Using the same `emit_event("error", ...)` pattern keeps log parsing consistent.

### What constitutes "empty"

**Decision**: `final_output` is considered empty when it is `None`, an empty string, or a string containing only whitespace.

**Rationale**: A whitespace-only response is equally useless as an empty one. The `str(final_output).strip()` check covers all three cases simply.

## Risks / Trade-offs

- **Risk**: A model intentionally returns minimal output (e.g., single word "Done") that is valid but nearly empty → **Mitigation**: We only fail on truly empty/whitespace-only output, not short output. Any non-whitespace content passes the check.
- **Risk**: The error event format diverges from the existing error resilience spec → **Mitigation**: Reuse the exact same `emit_event("error", {...})` format with the same field names, adding `"error_type": "empty_response"`.
