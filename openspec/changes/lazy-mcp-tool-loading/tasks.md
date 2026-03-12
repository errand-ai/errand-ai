## 1. Tool Visibility Context and Filter

- [x] 1.1 Create `task-runner/tool_registry.py` with `ToolVisibilityContext` dataclass containing `enabled_tools: set[str]` and `all_known_tools: set[str]`
- [x] 1.2 Implement `create_tool_filter()` that returns a `ToolFilterCallable` checking if tool name is in `enabled_tools` on the run context
- [x] 1.3 Implement `get_hot_list()` that reads `HOT_TOOLS` env var (comma-separated) or returns default set: `web_search`, `fetch_url`, `retain`, `recall`

## 2. Compact Tool Catalog

- [x] 2.1 Implement `build_tool_catalog()` that takes a list of connected MCP servers and the hot list, calls `list_tools()` on each, and returns an XML string with server names and tool name/description pairs (excluding hot-listed tools)
- [x] 2.2 Truncate tool descriptions to first sentence or 100 characters in catalog entries
- [x] 2.3 Return empty string if all tools are hot-listed (no catalog needed)

## 3. discover_tools Native Tool

- [x] 3.1 Implement `discover_tools` as a `@function_tool` that accepts a list of tool names, adds them to `enabled_tools` on the `RunContextWrapper` context, and returns confirmation of which were enabled vs not found
- [x] 3.2 Validate requested tool names against `all_known_tools` set to report unknown tools in the response

## 4. Wire into Task Runner main.py

- [x] 4.1 Update `connect_mcp_servers()` to accept a `tool_filter` callable and pass it to each `MCPServerStreamableHttp` constructor
- [x] 4.2 After connecting servers, call `build_tool_catalog()` and append the catalog to the system prompt (before `OUTPUT_INSTRUCTIONS`)
- [x] 4.3 Create `ToolVisibilityContext` initialized with hot list, wrap in `RunContextWrapper`, pass to `Runner.run_streamed()`
- [x] 4.4 Add `discover_tools` to the agent's `tools` list alongside `execute_command`
- [x] 4.5 Populate `all_known_tools` on the context from the `list_tools()` results used for catalog generation

## 5. Worker Changes

- [x] 5.1 Add `hot_tools` to the settings query in `get_task_settings()` and pass it as `HOT_TOOLS` env var to the container if configured

## 6. Tests

- [x] 6.1 Test `get_hot_list()` returns defaults when `HOT_TOOLS` not set and parses env var when set
- [x] 6.2 Test `create_tool_filter()` allows hot-listed tools through and blocks others, then allows tools after they're added to `enabled_tools`
- [x] 6.3 Test `build_tool_catalog()` generates correct XML, excludes hot-listed tools, and returns empty string when all tools are hot-listed
- [x] 6.4 Test `discover_tools` adds tool names to enabled set and reports unknown tools
- [x] 6.5 Test `connect_mcp_servers()` passes `tool_filter` to `MCPServerStreamableHttp`
- [x] 6.6 Integration test: agent with lazy loading can discover and call a deferred MCP tool
