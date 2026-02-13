## MODIFIED Requirements

### Requirement: Task runner outputs structured JSON to stdout
The task runner application SHALL extract and validate the agent's structured output JSON from the raw LLM response before printing it to stdout. The extraction logic SHALL attempt the following strategies in order: (1) parse the full stripped text as JSON directly, (2) locate a markdown code fence block (```` ```json...``` ```` or ```` ```...``` ````) anywhere in the text, extract its contents, and parse as JSON, (3) find the first `{` and last `}` in the text, extract that substring, and parse as JSON. The first strategy that produces a valid `TaskRunnerOutput` object (with `status`, `result`, and `questions` fields) SHALL be used. If no strategy succeeds, the task runner SHALL wrap the entire raw output as a completed result with the raw text in the `result` field. All other logging (agent reasoning, tool calls, errors) SHALL be written to stderr. The application SHALL exit with code 0 on successful completion and exit with code 1 on unrecoverable errors.

#### Scenario: Successful execution output
- **WHEN** the agent completes processing
- **THEN** stdout contains exactly one line of valid JSON matching the structured output schema, and the exit code is 0

#### Scenario: Agent error output
- **WHEN** the agent encounters an unrecoverable error (e.g. API authentication failure)
- **THEN** stderr contains error details, stdout is empty or contains an error JSON, and the exit code is 1

#### Scenario: Agent output with preamble text before JSON code fence
- **WHEN** the agent produces output like `Based on my analysis...\n\n` followed by ```` ```json\n{"status": "completed", "result": "report", "questions": []}\n``` ````
- **THEN** the task runner extracts the JSON from inside the code fence, validates it, and outputs the parsed JSON to stdout

#### Scenario: Agent output with preamble text before bare JSON
- **WHEN** the agent produces output like `Here is the result:\n{"status": "completed", "result": "done", "questions": []}`
- **THEN** the task runner extracts the JSON object from the text, validates it, and outputs the parsed JSON to stdout

#### Scenario: Agent output is bare JSON without any wrapping
- **WHEN** the agent produces output that is exactly `{"status": "completed", "result": "done", "questions": []}`
- **THEN** the task runner parses it directly and outputs it to stdout

#### Scenario: Agent output with code fence at start (existing behaviour)
- **WHEN** the agent produces output starting with ```` ```json\n{"status": "completed", "result": "done", "questions": []}\n``` ````
- **THEN** the task runner extracts the JSON from the code fence, validates it, and outputs the parsed JSON to stdout

#### Scenario: Agent output is not parseable as structured JSON
- **WHEN** the agent produces output that contains no valid `TaskRunnerOutput` JSON in any form
- **THEN** the task runner wraps the entire raw output as `{"status": "completed", "result": "<raw output>", "questions": []}` and outputs it to stdout
