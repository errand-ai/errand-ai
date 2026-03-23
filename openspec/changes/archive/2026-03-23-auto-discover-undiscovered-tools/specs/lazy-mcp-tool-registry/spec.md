## ADDED Requirements

### Requirement: Auto-enable undiscovered tools on ModelBehaviorError

The task-runner retry loop SHALL catch `ModelBehaviorError` exceptions and parse the tool name from the error message format "Tool {name} not found in agent {agent}". If the tool name exists in `all_known_tools` on the `ToolVisibilityContext` and the retry limit has not been reached, the tool SHALL be auto-added to `enabled_tools` and the agent run SHALL be retried. A warning SHALL be logged including the tool name and attempt number. If the tool name is not in `all_known_tools` or the retry limit is reached, the error SHALL be treated as fatal.

#### Scenario: Known but undiscovered tool is auto-enabled on retry

- **WHEN** the agent calls tool "gdrive_read_file" without discovering it, causing `ModelBehaviorError("Tool gdrive_read_file not found in agent TaskRunner")`, and "gdrive_read_file" is in `all_known_tools`, and attempts remain
- **THEN** the retry loop adds "gdrive_read_file" to `enabled_tools`, logs a warning, and retries the agent run

#### Scenario: Unknown tool causes fatal error

- **WHEN** the agent calls tool "nonexistent_tool" causing `ModelBehaviorError("Tool nonexistent_tool not found in agent TaskRunner")`, and "nonexistent_tool" is NOT in `all_known_tools`
- **THEN** the error is treated as fatal and the task-runner exits with code 1

#### Scenario: Retry limit reached

- **WHEN** the agent repeatedly fails with `ModelBehaviorError` and has exhausted all retry attempts
- **THEN** the error is treated as fatal and the task-runner exits with code 1
