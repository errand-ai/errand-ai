## ADDED Requirements

### Requirement: Empty final output validation

After the agent loop completes without exception, the task-runner SHALL validate that `result.final_output` is non-empty before reporting success. The output SHALL be considered empty when `final_output` is `None`, an empty string `""`, or a string containing only whitespace characters. When empty output is detected, the task-runner SHALL NOT report the task as completed. Instead, it SHALL emit a structured error event, report a failed status via the result callback and output file, and exit with code 1.

#### Scenario: Agent produces non-empty output

- **WHEN** the agent loop completes and `result.final_output` is `"Here is the result..."`
- **THEN** the task-runner processes the output normally and exits with code 0

#### Scenario: Agent produces empty string output

- **WHEN** the agent loop completes and `result.final_output` is `""`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Agent produces None output

- **WHEN** the agent loop completes and `result.final_output` is `None`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Agent produces whitespace-only output

- **WHEN** the agent loop completes and `result.final_output` is `"   \n  "`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Failed status reported via callback and output file

- **WHEN** empty output is detected and `RESULT_CALLBACK_URL` is configured
- **THEN** the result callback receives `{"status": "failed", "result": "", "error": "LLM returned empty response"}` and the output file contains the same payload
