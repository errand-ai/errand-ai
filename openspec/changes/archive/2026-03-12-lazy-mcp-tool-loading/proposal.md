## Why

The task-runner currently loads full tool schemas from all connected MCP servers at agent startup and injects them into the tool list sent to the LLM. As users add more MCP server configurations (manual servers, LiteLLM-discovered servers, Hindsight, platform-specific servers), the number of tools grows unboundedly. Each tool schema consumes ~500-1500 tokens, so a setup with 4+ MCP servers can burn 30-50K+ tokens before the agent processes a single user prompt — consuming context window that should be available for reasoning and tool results.

## What Changes

- Maintain a configurable "hot list" of tool names (e.g. `execute_command`, `web_search`, `fetch_url`) that are always visible to the agent and excluded from filtering
- Add a `tool_filter` to each MCP server connection in the task-runner that initially hides all MCP tools except hot-listed ones from the agent
- Inject a compact tool catalog into the system prompt listing available MCP server names and tool names with one-line descriptions (~50 tokens per server vs ~5K+ for full schemas)
- Add a `discover_tools` native tool that the agent calls to enable specific MCP tools by name — once enabled, tools appear natively in subsequent turns (no indirection on invocation)
- Use the OpenAI Agents SDK's `ToolFilterCallable` with `RunContextWrapper` state to track which tools have been enabled, evaluated per-turn against the cached tool list
- Enable lazy loading by default for all MCP server connections

## Capabilities

### New Capabilities
- `lazy-mcp-tool-registry`: Compact catalog generation, hot list management, tool visibility state management, dynamic tool filtering via OpenAI Agents SDK `ToolFilterCallable`, and the `discover_tools` native tool

### Modified Capabilities
- `task-runner-agent`: Agent configuration changes to wire up tool filters, system prompt catalog injection, and the discover_tools tool
- `task-worker`: Worker must generate the compact tool catalog (server names + tool name/description pairs) and pass it to the task-runner alongside the existing MCP configuration

## Impact

- **task-runner/** — new `tool_registry.py` module (filter, catalog, discover_tools tool); changes to `main.py` for wiring
- **errand/worker.py** — must connect to MCP servers at task prep time to fetch tool listings for the catalog, then pass the catalog to the container
- **Container interface** — new environment variable or input file for the tool catalog
- **Dependencies** — no new dependencies; uses existing OpenAI Agents SDK `ToolFilterCallable` and `MCPServerStreamableHttp` APIs
- **Backward compatible** — no config changes required; the agent sees the same tools, just loaded on demand instead of eagerly
