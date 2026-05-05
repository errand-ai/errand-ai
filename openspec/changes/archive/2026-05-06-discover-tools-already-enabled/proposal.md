## Why

When the agent calls `discover_tools` with the name of a native always-on tool (e.g. `read_file`, `write_file`, `execute_command`, `submit_result`), the function returns `"Not found: ..."` — the same response it gives for genuinely unknown names. We have observed in production (task `20433374-f075-4f2b-8165-0a14198e36d8`, "Research DevOps Contract Market") that this misleads the model into concluding the tools aren't loaded; it then refuses to do work it could trivially do, and reports a fake "tools unavailable" failure to the user. The agent had already used `read_file` successfully in the same session, so the tools were demonstrably available — only the discovery response misled it.

## What Changes

- `discover_tools` distinguishes three outcomes per requested name: **Enabled** (newly added to `enabled_tools`), **Already enabled (always-on)** (native `@function_tool` tools that are always visible), and **Not found** (no MCP tool with that name in the catalog).
- The set of always-on native tools is sourced from a single registry the runner already maintains, so adding/removing a native tool stays in one place.
- The phrasing in the response steers the model away from re-probing: it now sees that the tools it asked about are usable, instead of seeing "Not found" and giving up.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `lazy-mcp-tool-registry`: `discover_tools` response semantics — adds the "always-on" outcome for native function tools and updates the existing scenarios accordingly.

## Impact

- Code: `task-runner/tool_registry.py` (`discover_tools`, `ToolVisibilityContext`), `task-runner/main.py` (passes the always-on set when constructing the context).
- Tests: `task-runner/test_tool_registry.py` — new scenarios for always-on names; existing "Not found" scenario stays valid for genuinely unknown names.
- No API, DB, or deployment changes. No frontend impact. Server (`errand/`) is unaffected.
