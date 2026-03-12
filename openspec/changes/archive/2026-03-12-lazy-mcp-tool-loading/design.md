## Context

The task-runner uses the OpenAI Agents SDK to execute a ReAct agent with MCP tools. Currently, all MCP tool schemas are loaded eagerly — every tool from every connected server is injected into the LLM's tool list on the first turn. With a typical setup (errand, hindsight, litellm gateway, playwright, cloud storage), this can consume 30-50K+ tokens of context before the agent processes a single prompt.

The OpenAI Agents SDK provides a `ToolFilterCallable` mechanism on `MCPServerStreamableHttp` that allows per-turn, context-aware filtering of which tools are presented to the LLM. Combined with `cache_tools_list=True` (already in use), this enables lazy loading without modifying the SDK.

The worker currently builds `mcp.json` and passes it to the task-runner container. It does not currently connect to MCP servers itself — it only constructs the configuration.

## Goals / Non-Goals

**Goals:**

- Reduce token usage from MCP tool schemas by ~80-90% on the first turn
- Maintain full tool availability — every MCP tool remains callable, just discovered on demand
- Keep frequently-used tools (hot list) always available without discovery overhead
- Use the OpenAI Agents SDK's native `tool_filter` mechanism — no custom meta-tool protocol
- Zero configuration required — works out of the box with existing MCP server setups

**Non-Goals:**

- Per-server granularity for lazy vs eager loading (all servers use the same pattern)
- UI for managing the hot list (hardcoded initially, configurable via env var later if needed)
- Caching tool catalogs across task runs (each run builds its own catalog)
- Changing how the worker builds `mcp.json` — the catalog is generated task-runner-side

## Decisions

### Decision 1: Generate the tool catalog inside the task-runner, not the worker

**Choice:** The task-runner connects to MCP servers (as it already does), calls `list_tools()` on each, and builds the compact catalog itself.

**Alternative considered:** Have the worker connect to MCP servers to fetch tool listings, serialize a catalog file, and pass it to the container alongside `mcp.json`. This would require the worker to establish MCP connections it doesn't currently need, adding complexity and latency to task preparation.

**Rationale:** The task-runner already connects to all MCP servers in `connect_mcp_servers()` and even logs tool names diagnostically. Building the catalog here is a natural extension with no new infrastructure.

### Decision 2: Use `ToolFilterCallable` on `MCPServerStreamableHttp` with `RunContextWrapper` state

**Choice:** Each MCP server gets a `tool_filter` callable that checks whether a tool name is in the hot list or has been explicitly enabled via `discover_tools`. The enabled set is stored as a `set[str]` on a context object passed through `RunContextWrapper`.

**Alternative considered:** A `tool_search` meta-tool (like Claude Code / opencode) that returns full schemas and requires the LLM to call tools through the meta-tool. This adds indirection on every tool call and requires custom schema injection logic.

**Rationale:** The SDK's native filter mechanism means tools become natively callable once enabled — no indirection. The filter runs on every `list_tools()` call against the cached tool list, so enabling a tool takes effect on the next turn automatically.

### Decision 3: Compact catalog format in system prompt

**Choice:** Inject an XML block into the system prompt listing available MCP servers and their tools:

```xml
<available_mcp_tools>
Server: argocd
  - list_applications: List all ArgoCD applications
  - get_application: Get details of an ArgoCD application
  - sync_application: Sync an ArgoCD application

Server: hindsight
  - retain: Store a memory
  - recall: Search memories
  - reflect: Reflect on memories
</available_mcp_tools>
```

**Alternative considered:** JSON catalog format. XML is more token-efficient and matches the convention used by Claude Code's `<available-deferred-tools>` block.

**Rationale:** Simple, readable, low token count. The LLM can scan server/tool names and decide which to enable via `discover_tools`.

### Decision 4: Hot list is a hardcoded default set with env var override

**Choice:** Default hot list: `execute_command` (native tool, always available), plus MCP tools matching common names like `web_search`, `fetch_url`, `retain`, `recall`. The hot list is overridable via `HOT_TOOLS` environment variable (comma-separated tool names).

**Alternative considered:** No hot list (all tools deferred). This would force the agent to call `discover_tools` on every run even for basic capabilities, adding unnecessary turns.

**Rationale:** Most tasks need shell commands, web access, and memory. Having these always available avoids a wasted turn on discovery for common cases. The env var override lets users tune for their workload.

### Decision 5: `discover_tools` is a native `@function_tool`, not an MCP tool

**Choice:** `discover_tools` is defined as a `@function_tool` in the task-runner, taking a list of tool names and returning confirmation of which tools were enabled.

**Alternative considered:** Making it an MCP tool served by the errand backend. This would add a round-trip and couple the discovery mechanism to the backend.

**Rationale:** It's a local operation (mutate the enabled set on the run context). No network call needed. The function tool has direct access to `RunContextWrapper` via the SDK's context parameter.

## Risks / Trade-offs

**[Extra turn for non-hot-listed tools]** → The agent must call `discover_tools` before using a deferred tool, adding one turn of latency. Mitigated by the hot list covering the most common tools and by the catalog being visible in the system prompt so the agent can batch-enable multiple tools in one call.

**[Catalog staleness within a run]** → The catalog is built once at startup from `list_tools()`. If an MCP server's tool set changes mid-run, the catalog won't reflect it. Acceptable because task-runner runs are short-lived (minutes) and MCP server tool sets are stable.

**[Hot list mismatch]** → If a hot-listed tool name doesn't exist on any connected server, it's silently ignored (the filter just won't match). No error, no impact.

**[Token overhead of catalog]** → The catalog adds ~200-500 tokens to the system prompt. This is vastly less than the 30-50K+ saved by deferring full schemas. Net savings: ~95%+.
