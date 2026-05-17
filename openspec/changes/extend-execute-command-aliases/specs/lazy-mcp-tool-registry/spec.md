# Delta: lazy-mcp-tool-registry

## MODIFIED: Requirement — execute_command alias tools for common name hallucinations

The task-runner SHALL register a fixed set of always-on `@function_tool` shims that act as name aliases for `execute_command`. The alias set SHALL include at least `run_command`, `bash`, `shell`, `sh`, **and `executescript`**. Each alias SHALL accept the same `(command: str, working_directory: str = "/workspace")` signature as `execute_command` and SHALL invoke the same underlying implementation, returning the same output for the same input. Aliases SHALL be added to `ToolVisibilityContext.always_on_tools` at agent construction so they are visible to the tool filter on every turn. Aliases SHALL NOT be advertised in the system prompt, the `<available_mcp_tools>` catalog, or any user-facing tool listing — they exist solely as a compatibility surface for models that hallucinate the wrong shell-tool name.

## ADDED: Requirement — Harmony-suffix normalization in tool-not-found recovery

The task-runner's `ModelBehaviorError` recovery handler SHALL normalize the failing tool name before deciding whether the call can be rescued. Normalization SHALL strip any substring beginning at the first occurrence of the literal `<|` (the OpenAI Harmony format token prefix) through to the end of the tool name. If the normalized name is in `all_known_tools`, in the configured alias set, or equals `execute_command`, the handler SHALL re-dispatch the original call's arguments to the tool with the normalized name and SHALL log a structured event recording the original name, the normalized name, and the active model identifier. If the normalized name remains unknown, the handler SHALL fall through to the existing tool-not-found behaviour.

#### Scenario: Harmony-suffix on aliased shell tool

- **WHEN** the model calls `run_command<|channel|>json(command="echo hi")`
- **AND** the SDK raises `ModelBehaviorError("Tool run_command<|channel|>json not found in agent TaskRunner")`
- **THEN** the recovery handler normalizes the name to `run_command`, recognizes it as an `execute_command` alias, re-dispatches with the original arguments, and logs the normalization event including the model identifier

#### Scenario: Harmony-suffix on canonical tool name

- **WHEN** the model calls `execute_command<|message|>start(command="ls")`
- **AND** the SDK raises a tool-not-found error
- **THEN** the recovery handler normalizes the name to `execute_command`, re-dispatches with the original arguments, and logs the normalization event

#### Scenario: Unknown tool with Harmony suffix

- **WHEN** the model calls `frobnicate<|channel|>json(...)` and `frobnicate` is neither a known tool, alias, nor `execute_command`
- **THEN** the recovery handler logs the normalization attempt, falls through to the existing tool-not-found behaviour, and does NOT re-dispatch
