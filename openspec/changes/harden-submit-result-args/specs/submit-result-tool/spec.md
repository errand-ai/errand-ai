## MODIFIED Requirements

### Requirement: submit_result function tool

The task-runner SHALL provide a native `@function_tool` named `submit_result` that the LLM calls to deliver its task output. The tool SHALL accept the following arguments: `result` (string, required) containing the full task output with markdown formatting, `status` (string, optional, default `"completed"`) set to either `"completed"` or `"needs_input"`, and `questions` (list of strings, optional, default `[]`) for follow-up questions when status is `"needs_input"`. The `questions` parameter SHALL be declared as a non-nullable array so that the generated JSON Schema contains no `anyOf` branch and no `"null"` type. The tool SHALL additionally accept a JSON-encoded string for `questions` and decode it to a list of strings; a string that decodes to a JSON array SHALL have its elements coerced to strings, and a string that fails to decode or decodes to a non-array SHALL be preserved as a single-element list rather than discarded. The tool SHALL store the submitted values in the agent's run context (accessible after the run completes). The tool SHALL return a confirmation message: `"Result submitted successfully. You may now stop."`. If called multiple times, the last call SHALL win — only the most recent submission is used.

#### Scenario: Model calls submit_result with completed status

- **WHEN** the LLM calls `submit_result(result="# Report\n\nFindings here...", status="completed")`
- **THEN** the tool stores `{"status": "completed", "result": "# Report\n\nFindings here...", "questions": []}` in the run context and returns `"Result submitted successfully. You may now stop."`

#### Scenario: Model calls submit_result with needs_input status

- **WHEN** the LLM calls `submit_result(result="Partial findings so far...", status="needs_input", questions=["What date range?", "Which department?"])`
- **THEN** the tool stores the submission with status `"needs_input"` and the questions list in the run context

#### Scenario: Model calls submit_result multiple times

- **WHEN** the LLM calls `submit_result(result="Draft 1")` then later calls `submit_result(result="Final version")`
- **THEN** only the second submission (`"Final version"`) is used as the task output

#### Scenario: submit_result is always visible to the agent

- **WHEN** the agent is created with its native tools
- **THEN** `submit_result` is included alongside `discover_tools` and `execute_command` as a native function tool, visible on every turn without discovery

#### Scenario: Questions arrive as a JSON-encoded empty array

- **WHEN** the LLM calls `submit_result` with `questions` set to the string `"[]"`
- **THEN** the tool decodes it and stores `"questions": []` rather than rejecting the call

#### Scenario: Questions arrive as a JSON-encoded populated array

- **WHEN** the LLM calls `submit_result` with `questions` set to the string `"[\"What date range?\", \"Which department?\"]"`
- **THEN** the tool decodes it and stores `"questions": ["What date range?", "Which department?"]`

#### Scenario: Questions arrive as a string that is not valid JSON

- **WHEN** the LLM calls `submit_result` with `questions` set to the string `"What date range?"`
- **THEN** the tool stores `"questions": ["What date range?"]`, preserving the text as a single question rather than discarding it

#### Scenario: Questions arrive as a JSON-encoded non-array

- **WHEN** the LLM calls `submit_result` with `questions` set to the string `"{\"a\": 1}"`
- **THEN** the tool stores `"questions": ["{\"a\": 1}"]`, preserving the raw string as a single element

#### Scenario: Questions omitted entirely

- **WHEN** the LLM calls `submit_result(result="Done")` without supplying `questions`
- **THEN** the tool stores `"questions": []`

## ADDED Requirements

### Requirement: submit_result argument schema is guarded against nullable unions

The task-runner test suite SHALL assert the JSON Schema generated for the `submit_result` tool's `questions` parameter declares `"type": "array"` with string items, and contains neither an `anyOf` construct nor a `"null"` type. This guard exists because a nullable-union schema (`anyOf: [array, null]`, produced by a `list[str] | None` annotation) is serialised as a JSON-encoded string by at least one inference server used in production, causing every affected call to fail validation.

#### Scenario: Schema guard passes for a plain array parameter

- **WHEN** `questions` is annotated with a non-nullable array type whose JSON schema is a bare string array
- **THEN** the generated schema for `questions` is `{"type": "array", "items": {"type": "string"}, ...}` and the guard test passes

#### Scenario: Schema guard fails if a nullable union is reintroduced

- **WHEN** `questions` is annotated `list[str] | None`
- **THEN** the generated schema contains an `anyOf` branch with a `"null"` type and the guard test fails
