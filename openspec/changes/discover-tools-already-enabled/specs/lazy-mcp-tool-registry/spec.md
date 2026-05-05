## MODIFIED Requirements

### Requirement: discover_tools native tool

The task-runner SHALL define a `discover_tools` `@function_tool` that accepts a list of tool names to enable. For each name, the tool SHALL classify it into exactly one of three outcomes:

1. **Already enabled (always-on)** — the name is in `ToolVisibilityContext.always_on_tools` (the set of native `@function_tool` tools attached to the agent and always callable). No state change is required.
2. **Enabled** — the name is in `ToolVisibilityContext.all_known_tools` (an MCP tool from the catalog) and is added to `enabled_tools`.
3. **Not found** — the name is in neither set; no state changes.

Always-on classification SHALL take precedence over catalog membership when a name appears in both sets.

The response SHALL list each non-empty outcome as a clause, in the order `Enabled` → `Already enabled (always-on)` → `Not found`, joined by `". "`. The tool's description SHALL instruct the agent to consult the `<available_mcp_tools>` catalog in the system prompt to find tool names before calling `discover_tools`.

#### Scenario: Enable existing tools

- **WHEN** the agent calls `discover_tools(["list_applications", "get_application"])` and both tools exist on connected servers
- **THEN** both names are added to `enabled_tools` and the response confirms `Enabled: list_applications, get_application`

#### Scenario: Enable mix of existing and unknown tools

- **WHEN** the agent calls `discover_tools(["list_applications", "nonexistent_tool"])` and only `list_applications` exists in the catalog
- **THEN** `list_applications` is added to `enabled_tools` and the response says `Enabled: list_applications. Not found: nonexistent_tool`

#### Scenario: Enable already-enabled tool

- **WHEN** the agent calls `discover_tools(["retain"])` and `retain` is already in `enabled_tools` (hot-listed MCP tool, present in `all_known_tools`)
- **THEN** the response confirms `Enabled: retain` (idempotent, no error)

#### Scenario: Probe for native always-on tool

- **WHEN** the agent calls `discover_tools(["read_file"])` and `read_file` is in `always_on_tools`
- **THEN** the response confirms `Already enabled (always-on): read_file` and `enabled_tools` is unchanged

#### Scenario: Mixed probe for catalog, always-on, and unknown names

- **WHEN** the agent calls `discover_tools(["list_applications", "read_file", "made_up_tool"])`, `list_applications` is in `all_known_tools`, `read_file` is in `always_on_tools`, and `made_up_tool` is in neither
- **THEN** `list_applications` is added to `enabled_tools` and the response is `Enabled: list_applications. Already enabled (always-on): read_file. Not found: made_up_tool`

#### Scenario: Always-on classification wins over catalog membership

- **WHEN** the agent calls `discover_tools(["foo"])` and `"foo"` appears in both `always_on_tools` and `all_known_tools`
- **THEN** the response classifies `foo` under `Already enabled (always-on)` and does not add it to the `Enabled` clause

### Requirement: Tool visibility state via RunContextWrapper

The task-runner SHALL define a context class (e.g., `ToolVisibilityContext`) containing a `set[str]` of enabled tool names initialized with the hot list, a `set[str]` of all known catalog tool names (`all_known_tools`), and a `set[str]` of always-on native tool names (`always_on_tools`). This context SHALL be passed as the generic `TContext` parameter of `RunContextWrapper` to `Runner.run_streamed()`. The `enabled_tools` set SHALL be mutable so that the `discover_tools` tool can add tool names during execution. The `always_on_tools` set SHALL be populated at agent construction time from the same list of native `@function_tool` callables attached to the agent, ensuring both stay in sync.

#### Scenario: Initial state contains hot list

- **WHEN** the agent run starts with hot list `["retain", "recall"]`
- **THEN** the `ToolVisibilityContext.enabled_tools` set contains `{"retain", "recall"}`

#### Scenario: State mutated by discover_tools

- **WHEN** the agent calls `discover_tools` with tool names `["list_applications", "sync_application"]`
- **THEN** the `ToolVisibilityContext.enabled_tools` set adds both names and they become visible on the next turn

#### Scenario: always_on_tools populated from native tool list

- **WHEN** the agent is constructed with native `@function_tool` callables `[read_file, write_file, execute_command, submit_result, discover_tools]`
- **THEN** `ToolVisibilityContext.always_on_tools` contains the names of all five functions
