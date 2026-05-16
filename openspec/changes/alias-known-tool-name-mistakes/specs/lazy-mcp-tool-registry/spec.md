## ADDED Requirements

### Requirement: execute_command alias tools for common name hallucinations

The task-runner SHALL register a fixed set of always-on `@function_tool` shims that act as name aliases for `execute_command`. The alias set SHALL include at least `run_command`, `bash`, `shell`, and `sh`. Each alias SHALL accept the same `(command: str, working_directory: str = "/workspace")` signature as `execute_command` and SHALL invoke the same underlying implementation, returning the same output for the same input. Aliases SHALL be added to `ToolVisibilityContext.always_on_tools` at agent construction so they are visible to the tool filter on every turn. Aliases SHALL NOT be advertised in the system prompt, the `<available_mcp_tools>` catalog, or any user-facing tool listing — they exist solely as a compatibility surface for models that hallucinate the wrong shell-tool name.

Aliases SHALL emit `tool_call` and `tool_result` structured events under the alias name actually called (e.g. `{"tool": "run_command", ...}`), not under the canonical `execute_command` name, so production telemetry preserves the signal about which aliases fire.

#### Scenario: run_command alias delegates to execute_command

- **WHEN** the agent calls `run_command(command="ls /workspace")`
- **THEN** the same command runs with the same working directory and the same output is returned as if the agent had called `execute_command(command="ls /workspace")`

#### Scenario: bash alias delegates to execute_command

- **WHEN** the agent calls `bash(command="echo hello", working_directory="/tmp")`
- **THEN** the command runs in `/tmp` and the response equals the output of `execute_command(command="echo hello", working_directory="/tmp")`

#### Scenario: All aliases registered as always-on

- **WHEN** the agent is constructed
- **THEN** `ToolVisibilityContext.always_on_tools` contains `execute_command` and every alias name in the alias set (at minimum: `run_command`, `bash`, `shell`, `sh`)

#### Scenario: Aliases absent from the MCP catalog

- **WHEN** the task-runner builds the `<available_mcp_tools>` catalog from connected MCP servers
- **THEN** no alias name appears in the catalog (the catalog is generated solely from MCP-server tool lists, never from native `@function_tool` shims)

#### Scenario: Structured event uses the alias name actually called

- **WHEN** the agent calls `bash(command="ls")` and the call produces a `tool_call` structured event
- **THEN** the event payload contains `{"tool": "bash", "args": {"command": "ls"}, ...}` — not `{"tool": "execute_command", ...}`

#### Scenario: discover_tools probe for an alias name is classified as always-on

- **WHEN** the agent calls `discover_tools(["run_command"])` and `run_command` is registered as an alias
- **THEN** the response is `Already enabled (always-on): run_command` and `enabled_tools` is unchanged
