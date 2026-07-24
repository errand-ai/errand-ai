## Purpose

Lazy MCP tool loading system — manages a compact tool catalog, hot list, tool visibility state, and the `discover_tools` native tool for on-demand tool activation.

## Requirements

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

The task-runner SHALL define a context class (e.g., `ToolVisibilityContext`) containing a `set[str]` of enabled tool names initialized with the hot list, a `set[str]` of all known catalog tool names (`all_known_tools`), a `set[str]` of always-on native tool names (`always_on_tools`), and a `dict[str, str]` of installed skills (`installed_skills`) mapping skill name to the absolute path of its `SKILL.md` file. This context SHALL be passed as the generic `TContext` parameter of `RunContextWrapper` to `Runner.run_streamed()`. The `enabled_tools` set SHALL be mutable so that the `discover_tools` tool can add tool names during execution. The `always_on_tools` set SHALL be populated at agent construction time from the same list of native `@function_tool` callables attached to the agent, ensuring both stay in sync. The `installed_skills` dict SHALL be populated at agent construction time by scanning `/workspace/skills/*/SKILL.md`; the dict SHALL be empty when no skills directory exists.

#### Scenario: Initial state contains hot list

- **WHEN** the agent run starts with hot list `["retain", "recall"]`
- **THEN** the `ToolVisibilityContext.enabled_tools` set contains `{"retain", "recall"}`

#### Scenario: State mutated by discover_tools

- **WHEN** the agent calls `discover_tools` with tool names `["list_applications", "sync_application"]`
- **THEN** the `ToolVisibilityContext.enabled_tools` set adds both names and they become visible on the next turn

#### Scenario: always_on_tools populated from native tool list

- **WHEN** the agent is constructed with native `@function_tool` callables `[read_file, write_file, execute_command, submit_result, discover_tools]`
- **THEN** `ToolVisibilityContext.always_on_tools` contains the names of all five functions

#### Scenario: installed_skills populated from /workspace/skills

- **WHEN** the agent is constructed and `/workspace/skills/` contains `tweet-publisher/SKILL.md` and `gws-drive/SKILL.md`
- **THEN** `ToolVisibilityContext.installed_skills` equals `{"tweet-publisher": "/workspace/skills/tweet-publisher/SKILL.md", "gws-drive": "/workspace/skills/gws-drive/SKILL.md"}`

#### Scenario: installed_skills empty when no skills directory

- **WHEN** the agent is constructed and `/workspace/skills/` does not exist
- **THEN** `ToolVisibilityContext.installed_skills` is an empty dict

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

The task-runner SHALL define a `discover_tools` `@function_tool` that accepts a list of tool names to enable. For each name, the tool SHALL classify it into exactly one of four outcomes:

1. **Already enabled (always-on)** — the name is in `ToolVisibilityContext.always_on_tools` (the set of native `@function_tool` tools attached to the agent and always callable). No state change is required.
2. **Enabled** — the name is in `ToolVisibilityContext.all_known_tools` (an MCP tool from the catalog) and is added to `enabled_tools`.
3. **Loaded skill** — the name is not a tool but matches a key in `ToolVisibilityContext.installed_skills`. The tool SHALL read the corresponding `SKILL.md` file synchronously and include its full content, inline in the response, inside a delimited block. No tool state changes.
4. **Not found** — the name is in none of the above sets; no state changes.

Outcome precedence SHALL be: `always_on_tools` > `all_known_tools` > `installed_skills` > `Not found`. A name appearing in more than one set takes the highest-priority outcome.

The response SHALL list each non-empty outcome as a clause, in the order `Enabled` → `Already enabled (always-on)` → `Loaded skill` → `Not found`, joined by `". "`. The `Loaded skill` clause SHALL be followed by the SKILL.md content delimited by `--- <absolute-path> ---` and `--- end skill ---` markers. The tool's description SHALL instruct the agent to consult the `<available_mcp_tools>` catalog in the system prompt to find tool names before calling `discover_tools`.

If a SKILL.md file recorded in `installed_skills` cannot be read at call time (e.g., deleted, permissions error), the tool SHALL classify that name as `Not found` rather than raising an exception.

#### Scenario: Enable existing tools

- **WHEN** the agent calls `discover_tools(["list_applications", "get_application"])` and both tools exist on connected servers
- **THEN** both names are added to `enabled_tools` and the response confirms `Enabled: list_applications, get_application`

#### Scenario: Enable mix of existing and unknown tools

- **WHEN** the agent calls `discover_tools(["list_applications", "nonexistent_tool"])` and only `list_applications` exists in the catalog and `nonexistent_tool` is not an installed skill
- **THEN** `list_applications` is added to `enabled_tools` and the response says `Enabled: list_applications. Not found: nonexistent_tool`

#### Scenario: Enable already-enabled tool

- **WHEN** the agent calls `discover_tools(["retain"])` and `retain` is already in `enabled_tools` (hot-listed MCP tool, present in `all_known_tools`)
- **THEN** the response confirms `Enabled: retain` (idempotent, no error)

#### Scenario: Probe for native always-on tool

- **WHEN** the agent calls `discover_tools(["read_file"])` and `read_file` is in `always_on_tools`
- **THEN** the response confirms `Already enabled (always-on): read_file` and `enabled_tools` is unchanged

#### Scenario: Probe matches an installed skill — SKILL.md inlined

- **WHEN** the agent calls `discover_tools(["tweet-publisher"])`, `tweet-publisher` is not a tool, and `/workspace/skills/tweet-publisher/SKILL.md` exists with content `---\nname: tweet-publisher\ndescription: Post approved tweets\n---\n\n## Steps\n1. Read approved tweets...`
- **THEN** `enabled_tools` is unchanged and the response is `Loaded skill: tweet-publisher\n\n--- /workspace/skills/tweet-publisher/SKILL.md ---\n---\nname: tweet-publisher\ndescription: Post approved tweets\n---\n\n## Steps\n1. Read approved tweets...\n--- end skill ---`

#### Scenario: Mixed probe across tools, skills, and unknown names

- **WHEN** the agent calls `discover_tools(["list_applications", "tweet-publisher", "made_up_name"])`, `list_applications` is in `all_known_tools`, `tweet-publisher` is in `installed_skills`, and `made_up_name` is in none of the sets
- **THEN** `list_applications` is added to `enabled_tools` and the response is `Enabled: list_applications. Loaded skill: tweet-publisher\n\n--- /workspace/skills/tweet-publisher/SKILL.md ---\n<contents>\n--- end skill ---. Not found: made_up_name`

#### Scenario: Mixed probe for catalog, always-on, and unknown names

- **WHEN** the agent calls `discover_tools(["list_applications", "read_file", "made_up_tool"])`, `list_applications` is in `all_known_tools`, `read_file` is in `always_on_tools`, and `made_up_tool` is in neither tools nor skills
- **THEN** `list_applications` is added to `enabled_tools` and the response is `Enabled: list_applications. Already enabled (always-on): read_file. Not found: made_up_tool`

#### Scenario: Always-on classification wins over catalog membership

- **WHEN** the agent calls `discover_tools(["foo"])` and `"foo"` appears in both `always_on_tools` and `all_known_tools`
- **THEN** the response classifies `foo` under `Already enabled (always-on)` and does not add it to the `Enabled` clause

#### Scenario: Tool name takes precedence over identically-named skill

- **WHEN** the agent calls `discover_tools(["tweet-publisher"])`, `tweet-publisher` is present in both `all_known_tools` (as an MCP tool) and `installed_skills`
- **THEN** `tweet-publisher` is added to `enabled_tools` and the response is `Enabled: tweet-publisher` — the skill is NOT loaded

#### Scenario: Installed skill SKILL.md unreadable at call time

- **WHEN** the agent calls `discover_tools(["tweet-publisher"])`, `tweet-publisher` is in `installed_skills`, but the SKILL.md file was deleted after startup
- **THEN** the response is `Not found: tweet-publisher` (no exception is raised)

#### Scenario: Multiple skill matches in one call

- **WHEN** the agent calls `discover_tools(["tweet-publisher", "gws-drive"])` and both are installed skills with readable SKILL.md files
- **THEN** the response is `Loaded skill: tweet-publisher, gws-drive` followed by both SKILL.md blocks, each delimited by its own `--- <path> ---` / `--- end skill ---` markers, in the order the names were passed

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

### Requirement: Harmony-suffix normalization in tool-not-found recovery

The task-runner's `ModelBehaviorError` recovery handler SHALL normalize the failing tool name before deciding whether the failure can be rescued. Normalization SHALL strip any substring beginning at the first occurrence of the literal `<|` (the OpenAI Harmony format token prefix) through to the end of the tool name. If the normalized name is in `all_known_tools`, in the configured alias set, or equals `execute_command`, the handler SHALL retry the agent run (giving the model another opportunity to emit the bare name on its next turn) without consuming a slot from `MAX_AGENT_RETRIES`, and SHALL log a structured event recording the original name, the normalized name, and the active model identifier. Recovery for a given `(original, normalized)` pair SHALL be bounded by a configurable per-pair cap; once exceeded, the handler SHALL fall through to normal `MAX_AGENT_RETRIES` accounting so a model emitting the same bad token cannot loop indefinitely. If the normalized name is not recognized, the handler SHALL fall through to the existing tool-not-found behaviour and SHALL NOT log a normalization event for the failed lookup.

#### Scenario: Harmony-suffix on aliased shell tool

- **WHEN** the model calls `run_command<|channel|>json(command="echo hi")`
- **AND** the SDK raises `ModelBehaviorError("Tool run_command<|channel|>json not found in agent TaskRunner")`
- **THEN** the recovery handler normalizes the name to `run_command`, recognizes it as an `execute_command` alias, retries the agent run without decrementing `MAX_AGENT_RETRIES`, and logs the normalization event including the model identifier and the attempt count for this pair

#### Scenario: Harmony-suffix on canonical tool name

- **WHEN** the model calls `execute_command<|message|>start(command="ls")`
- **AND** the SDK raises a tool-not-found error
- **THEN** the recovery handler normalizes the name to `execute_command`, retries the agent run without decrementing `MAX_AGENT_RETRIES`, and logs the normalization event

#### Scenario: Unknown tool with Harmony suffix

- **WHEN** the model calls `frobnicate<|channel|>json(...)` and `frobnicate` is neither a known tool, alias, nor `execute_command`
- **THEN** the recovery handler does NOT retry and does NOT emit a normalization event; the failure falls through to the existing tool-not-found handling

#### Scenario: Same suffixed tool name emitted repeatedly

- **WHEN** the model calls `run_command<|channel|>json(...)` and the recovery handler has already fired for that `(original, normalized)` pair the maximum permitted times
- **THEN** the recovery handler logs a cap-reached warning and falls through to normal `MAX_AGENT_RETRIES` accounting, ensuring the run terminates rather than looping indefinitely
