## MODIFIED Requirements

### Requirement: Tool filter callable

The task-runner SHALL define a `ToolFilterCallable` that receives `ToolFilterContext` and an `MCPTool`, and returns `True` if the tool's name is in the `enabled_tools` set on the run context, `False` otherwise. If the tool's name is not in `enabled_tools` but IS in `all_known_tools`, the filter SHALL auto-add the tool name to `enabled_tools`, log a warning message including the tool name, and return `True`. This filter SHALL be passed as the `tool_filter` parameter to each `MCPServerStreamableHttp` constructor.

#### Scenario: Hot-listed tool passes filter

- **WHEN** the filter evaluates tool "retain" and "retain" is in `enabled_tools`
- **THEN** the filter returns `True` and the tool is visible to the agent

#### Scenario: Non-enabled tool blocked by filter

- **WHEN** the filter evaluates tool "nonexistent_tool" and "nonexistent_tool" is not in `enabled_tools` and not in `all_known_tools`
- **THEN** the filter returns `False` and the tool is hidden from the agent

#### Scenario: Tool enabled after discovery

- **WHEN** the agent previously called `discover_tools(["sync_application"])` and the filter evaluates "sync_application" on the next turn
- **THEN** the filter returns `True` because "sync_application" was added to `enabled_tools`

#### Scenario: Known but undiscovered tool is auto-enabled

- **WHEN** the filter evaluates tool "gdrive_read_file" and "gdrive_read_file" is not in `enabled_tools` but IS in `all_known_tools`
- **THEN** the filter adds "gdrive_read_file" to `enabled_tools`, logs a warning "Auto-enabled undiscovered tool: gdrive_read_file", and returns `True`

#### Scenario: Auto-enabled tool remains enabled on subsequent calls

- **WHEN** tool "gdrive_read_file" was auto-enabled by the filter on a previous turn and the filter evaluates it again
- **THEN** the filter returns `True` immediately (the tool is now in `enabled_tools`) with no additional warning log
