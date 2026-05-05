## Context

The task-runner uses a lazy-loading MCP tool registry (`task-runner/tool_registry.py`). At startup it builds a catalog of MCP-server-provided tools and tracks them in `ToolVisibilityContext.all_known_tools`. The agent then calls `discover_tools(names)` to flip names from "in catalog, hidden" to "enabled". Hot-listed MCP tools (`web_search`, `fetch_url`, `retain`, `recall`) are pre-enabled but still appear in `all_known_tools`, so a redundant probe returns "Enabled" idempotently.

Native `@function_tool` tools — `read_file`, `write_file`, `edit_file`, `execute_command`, `submit_result`, `discover_tools` itself, etc. — are different. They're attached to the agent directly (not via an MCP server), are always callable, and never appear in `all_known_tools`. When the agent probes for them, the current code falls through to the `not_found` branch and returns `"Not found: read_file"`. The model interprets that as "the tool is not loaded" and stops using it, even when it has used it successfully moments earlier.

Production evidence: task `20433374-...` issued nine separate `discover_tools` probes for variants of `read_file`/`write_file`/`execute_command`, got "Not found" each time, then declared the tools unavailable and exited — between probes it had successfully called `read_file` on `/workspace/skills/gws-drive/SKILL.md`.

## Goals / Non-Goals

**Goals:**
- A `discover_tools` probe for a native always-on tool returns wording that tells the model the tool is usable right now.
- The set of always-on names is sourced from a single registry so it stays in sync as native tools are added or removed.
- Genuinely unknown names still return "Not found" — no regressions for the catalog-miss case.

**Non-Goals:**
- Re-architecting how native tools are attached to the agent. They stay outside `all_known_tools`.
- Auto-listing native tools in the `<available_mcp_tools>` catalog. The catalog is for MCP tools that need explicit enablement; natives are out of scope.
- Changing the `discover_tools` parameter shape or adding new parameters.
- Suppressing future probes — if the model probes again, the response should remain helpful, but we are not adding state to remember "already told the model about this".

## Decisions

### Source of truth for the always-on set

**Decision**: Add an `always_on_tools: set[str]` field to `ToolVisibilityContext`, populated at agent construction time in `task-runner/main.py` from the same list of native `@function_tool` callables that are attached to the agent. `discover_tools` consults that set.

**Alternatives considered:**
- *Hard-code a constant in `tool_registry.py`*: drifts the moment someone adds a native tool. Rejected.
- *Inspect the agent at call time*: `discover_tools` doesn't have a handle to the agent, only to the run context. Adding one would widen the context coupling. Rejected.
- *Treat any name not in `all_known_tools` as "always-on" and trust the model*: would lie to the model about genuinely unknown names. Rejected.

### Response wording

**Decision**: When at least one requested name is always-on, the response includes a third clause: `Already enabled (always-on): read_file, write_file`. Order in the response: `Enabled` → `Already enabled (always-on)` → `Not found`. Clauses are joined with `". "` to match the existing pattern.

Example responses:
- `discover_tools(["read_file"])` → `Already enabled (always-on): read_file`
- `discover_tools(["list_applications", "read_file", "made_up"])` → `Enabled: list_applications. Already enabled (always-on): read_file. Not found: made_up`

### Idempotency

**Decision**: Always-on detection takes precedence over catalog membership. If a tool name appears in both `always_on_tools` and `all_known_tools` (shouldn't happen in practice, but possible if a future native tool shadows an MCP name), the always-on label wins — it is the more accurate description of state.

## Risks / Trade-offs

- **Risk**: Forgetting to add a new native tool to `always_on_tools` reintroduces the original bug for that tool. **Mitigation**: derive `always_on_tools` from the same list of `@function_tool` callables that gets attached to the agent in `main.py`, so a single source of truth populates both.
- **Risk**: The model treats "Already enabled (always-on)" as a license to spam `discover_tools` probes thinking they're cheap. **Mitigation**: `discover_tools` is already cheap (in-memory set membership). The cost we are eliminating is the much larger cost of the agent giving up entirely.
- **Trade-off**: Three response shapes instead of two means the parser/agent has slightly more to parse. Acceptable — the model handles natural-language responses well, and the new clause is structurally identical to the existing two.
