## ADDED Requirements

### Requirement: Empty response error event emission

When the agent loop completes without exception but produces empty output, the task-runner SHALL emit a structured error event. The event format SHALL be `{"type": "error", "data": {"message": "LLM returned empty response", "error_type": "empty_response", "error_class": "EmptyResponseError"}}`. This event SHALL be emitted via the existing `emit_event()` mechanism to stderr, consistent with the error event format defined in the structured error event emission requirement.

#### Scenario: Error event emitted for empty response

- **WHEN** the agent loop completes and `result.final_output` is empty
- **THEN** an error event is emitted to stderr with `"type": "error"`, `"error_type": "empty_response"`, and `"error_class": "EmptyResponseError"`

#### Scenario: Error event format matches existing error events

- **WHEN** an empty response error event is emitted
- **THEN** the event JSON contains the same fields as other error events: `message`, `error_type`, and `error_class`
