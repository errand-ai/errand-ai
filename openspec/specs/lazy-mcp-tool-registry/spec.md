## Purpose

Lazy MCP tool loading system — manages a compact tool catalog, hot list, tool visibility state, and the `discover_tools` native tool for on-demand tool activation.

## ADDED Requirements

### Requirement: Compact tool catalog generation

The task-runner SHALL generate a compact tool catalog from all connected MCP servers after connection. For each server, the catalog SHALL include the server name and a list of tool entries containing the tool name and its description (first sentence only, truncated to 100 characters). The catalog SHALL be formatted as an XML block (`<available_mcp_tools>`) suitable for injection into the system prompt. Tools that are on the hot list SHALL be excluded from the catalog (they are already visible to the agent). If all tools from all servers are on the hot list, the catalog block SHALL be omitted entirely.

#### Scenario: Catalog with multiple servers

- **WHEN** the task-runner connects to servers "argocd" (5 tools) and "hindsight" (3 tools) with hot list `["retain", "recall"]`
- **THEN** the catalog lists "argocd" with 5 tool entries and "hindsight" with 1 tool entry (reflect), excluding retain and recall

#### Scenario: All tools hot-listed

- **WHEN** the task-runner connects to one server with 2 tools and both are on the hot list
- **THEN** no `<available_mcp_tools>` block is injected into the system prompt

#### Scenario: Server with no non-hot tools

- **WHEN** a server's tools are all on the hot list
- **THEN** that server is omitted from the catalog entirely

### Requirement: Hot list management

The task-runner SHALL maintain a hot list of tool names that are always visible to the agent (excluded from filtering). The default hot list SHALL include: `web_search`, `fetch_url`, `retain`, `recall`. The hot list SHALL be overridable via the `HOT_TOOLS` environment variable as a comma-separated list of tool names. The native `execute_command` tool is always available (it is a `@function_tool`, not an MCP tool) and does not need to be on the hot list.

#### Scenario: Default hot list

- **WHEN** `HOT_TOOLS` is not set
- **THEN** the hot list contains `web_search`, `fetch_url`, `retain`, `recall`

#### Scenario: Custom hot list via environment variable

- **WHEN** `HOT_TOOLS` is set to `"retain,recall,list_applications"`
- **THEN** the hot list contains exactly `retain`, `recall`, `list_applications`

#### Scenario: Hot-listed tool not present on any server

- **WHEN** the hot list includes `web_search` but no connected MCP server provides a tool named `web_search`
- **THEN** the filter silently ignores `web_search` with no error

### Requirement: Tool visibility state via RunContextWrapper

The task-runner SHALL define a context class (e.g., `ToolVisibilityContext`) containing a `set[str]` of enabled tool names, initialized with the hot list. This context SHALL be passed as the generic `TContext` parameter of `RunContextWrapper` to `Runner.run_streamed()`. The enabled set SHALL be mutable so that the `discover_tools` tool can add tool names during execution.

#### Scenario: Initial state contains hot list

- **WHEN** the agent run starts with hot list `["retain", "recall"]`
- **THEN** the `ToolVisibilityContext.enabled_tools` set contains `{"retain", "recall"}`

#### Scenario: State mutated by discover_tools

- **WHEN** the agent calls `discover_tools` with tool names `["list_applications", "sync_application"]`
- **THEN** the `ToolVisibilityContext.enabled_tools` set adds both names and they become visible on the next turn

### Requirement: Tool filter callable

The task-runner SHALL define a `ToolFilterCallable` that receives `ToolFilterContext` and an `MCPTool`, and returns `True` if the tool's name is in the `enabled_tools` set on the run context, `False` otherwise. This filter SHALL be passed as the `tool_filter` parameter to each `MCPServerStreamableHttp` constructor.

#### Scenario: Hot-listed tool passes filter

- **WHEN** the filter evaluates tool "retain" and "retain" is in `enabled_tools`
- **THEN** the filter returns `True` and the tool is visible to the agent

#### Scenario: Non-enabled tool blocked by filter

- **WHEN** the filter evaluates tool "sync_application" and "sync_application" is not in `enabled_tools`
- **THEN** the filter returns `False` and the tool is hidden from the agent

#### Scenario: Tool enabled after discovery

- **WHEN** the agent previously called `discover_tools(["sync_application"])` and the filter evaluates "sync_application" on the next turn
- **THEN** the filter returns `True` because "sync_application" was added to `enabled_tools`

### Requirement: discover_tools native tool

The task-runner SHALL define a `discover_tools` `@function_tool` that accepts a list of tool names to enable. The tool SHALL add each name to the `enabled_tools` set on the `RunContextWrapper` context. The tool SHALL return a confirmation message listing which tools were enabled and which were not found on any connected server. The tool's description SHALL instruct the agent to consult the `<available_mcp_tools>` catalog in the system prompt to find tool names before calling `discover_tools`.

#### Scenario: Enable existing tools

- **WHEN** the agent calls `discover_tools(["list_applications", "get_application"])` and both tools exist on connected servers
- **THEN** both names are added to `enabled_tools` and the response confirms "Enabled: list_applications, get_application"

#### Scenario: Enable mix of existing and unknown tools

- **WHEN** the agent calls `discover_tools(["list_applications", "nonexistent_tool"])` and only `list_applications` exists
- **THEN** `list_applications` is added to `enabled_tools` and the response says "Enabled: list_applications. Not found: nonexistent_tool"

#### Scenario: Enable already-enabled tool

- **WHEN** the agent calls `discover_tools(["retain"])` and `retain` is already in `enabled_tools`
- **THEN** the response confirms "Enabled: retain" (idempotent, no error)

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
