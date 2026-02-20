## MODIFIED Requirements

### Requirement: Task runner outputs structured JSON to stdout
The task runner application SHALL output the agent's structured response as a single JSON line to stdout. Additionally, the task runner SHALL write the same structured JSON to `/output/result.json` if the `/output` directory exists. If the `/output` directory does not exist, the file write SHALL be skipped (backward compatibility with runtimes that don't mount an output volume). The stdout output and file content SHALL be identical. All structured events (agent reasoning, tool calls, errors) SHALL continue to be written to stderr. The application SHALL exit with code 0 on successful completion and exit with code 1 on unrecoverable errors.

#### Scenario: Successful execution output to stdout and file
- **WHEN** the agent completes processing and `/output` directory exists
- **THEN** stdout contains exactly one line of valid JSON matching the `TaskRunnerOutput` schema, `/output/result.json` contains the same JSON, and the exit code is 0

#### Scenario: Successful execution without output directory
- **WHEN** the agent completes processing and `/output` directory does not exist
- **THEN** stdout contains the JSON output, no file is written, and the exit code is 0

#### Scenario: Agent error output
- **WHEN** the agent encounters an unrecoverable error
- **THEN** stderr contains an `error` event with the failure details, stdout is empty, no result.json is written, and the exit code is 1
