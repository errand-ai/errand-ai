## ADDED Requirements

### Requirement: submit_result function tool

The task-runner SHALL provide a native `@function_tool` named `submit_result` that the LLM calls to deliver its task output. The tool SHALL accept the following arguments: `result` (string, required) containing the full task output with markdown formatting, `status` (string, optional, default `"completed"`) set to either `"completed"` or `"needs_input"`, and `questions` (list of strings, optional, default `[]`) for follow-up questions when status is `"needs_input"`. The tool SHALL store the submitted values in the agent's run context (accessible after the run completes). The tool SHALL return a confirmation message: `"Result submitted successfully. You may now stop."`. If called multiple times, the last call SHALL win — only the most recent submission is used.

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

### Requirement: Output extraction priority

After the agent run completes, the task-runner SHALL extract the task output using the following priority order: (1) if `submit_result` was called during the run, use its stored result and status, (2) if `submit_result` was not called but `result.final_output` contains valid JSON matching the `TaskRunnerOutput` schema, extract from text (backward compatibility), (3) if `result.final_output` contains non-empty text that is not valid `TaskRunnerOutput` JSON, wrap it as `{"status": "completed", "result": <raw_text>, "questions": []}`, (4) if all of the above yield no result, trigger the empty-response nudge.

#### Scenario: submit_result output preferred over text output

- **WHEN** the LLM calls `submit_result(result="Tool result")` AND also produces final text output `{"status": "completed", "result": "Text result"}`
- **THEN** the task-runner uses `"Tool result"` (from submit_result), not `"Text result"`

#### Scenario: Text JSON fallback when submit_result not called

- **WHEN** the LLM does not call `submit_result` but produces `{"status": "completed", "result": "Some findings"}` as its final text
- **THEN** the task-runner extracts the result from the text JSON (backward compatibility)

#### Scenario: Raw text fallback

- **WHEN** the LLM does not call `submit_result` and produces plain text `"Here are the results..."` as its final output
- **THEN** the task-runner wraps it as `{"status": "completed", "result": "Here are the results...", "questions": []}`

### Requirement: Empty-response nudge

When the agent run completes with empty output (no `submit_result` call and empty/whitespace-only `final_output`), the task-runner SHALL check whether the agent called any tools during the run. If tools were called (indicating the agent did work), the task-runner SHALL inject a follow-up user message prompting the agent to call `submit_result`, and re-run the agent for one additional attempt. The nudge message SHALL be: `"You completed your work but didn't deliver the result to the user. Call submit_result now with a comprehensive summary of what you found or accomplished."`. The nudge attempt SHALL NOT count toward `MAX_AGENT_RETRIES`. If the nudge attempt also produces no result, the task-runner SHALL fall back to the existing behavior: emit an error event, report failed status, and exit with code 1.

#### Scenario: Nudge after retain-then-empty pattern

- **WHEN** the agent calls `retain()` and then produces an empty `final_output`, and `submit_result` was not called
- **THEN** the task-runner detects tools were called, injects the nudge message, and re-runs the agent

#### Scenario: Nudge succeeds

- **WHEN** the nudge message is injected and the agent responds by calling `submit_result(result="...")`
- **THEN** the task-runner uses the submitted result and exits with code 0

#### Scenario: Nudge fails

- **WHEN** the nudge message is injected and the agent still produces empty output without calling `submit_result`
- **THEN** the task-runner emits an error event with `"error_type": "empty_response"`, reports a failed status, and exits with code 1

#### Scenario: Empty output with no tool calls

- **WHEN** the agent produces empty output and called zero tools during the run
- **THEN** the task-runner SHALL NOT nudge (no work was done to summarize) and SHALL immediately emit an error event and exit with code 1

### Requirement: Updated output instructions in system prompt

The `OUTPUT_INSTRUCTIONS` constant SHALL instruct models to call `submit_result()` when their task is complete. The instructions SHALL explicitly differentiate between `retain` (saves to persistent memory for future tasks) and `submit_result` (delivers the result to the user). The instructions SHALL state that every task should call `retain` before `submit_result` to build persistent memory. The instructions SHALL include a brief fallback note that if `submit_result` is unavailable, the model may respond with a JSON object, but the tool is the preferred method.

#### Scenario: Output instructions mention submit_result

- **WHEN** the system prompt is assembled for the agent
- **THEN** the `OUTPUT_INSTRUCTIONS` section instructs the model to call `submit_result(result=..., status=...)` when done and to call `retain()` before submitting to build persistent memory

#### Scenario: Output instructions differentiate retain from submit_result

- **WHEN** the model reads the system prompt
- **THEN** the instructions clearly state that `retain()` saves information for future tasks (memory) while `submit_result()` delivers the output to the user (task completion)
