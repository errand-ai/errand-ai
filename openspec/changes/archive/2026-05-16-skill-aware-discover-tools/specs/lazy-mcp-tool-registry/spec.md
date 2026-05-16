## MODIFIED Requirements

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
