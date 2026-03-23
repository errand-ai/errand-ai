## Context

The task-runner uses lazy MCP tool loading: tool schemas are only loaded into the agent's context when explicitly discovered via `discover_tools`. A tool filter (`ToolFilterCallable`) on each MCP server controls visibility — tools not in `enabled_tools` are hidden.

Currently, if a model calls an undiscovered tool, the OpenAI Agents SDK raises `ModelBehaviorError` because the tool isn't in the agent's tool list. The retry loop re-runs the entire agent from scratch, but weaker models repeat the same mistake, wasting all 3 attempts.

## Goals / Non-Goals

**Goals:**
- Auto-enable known MCP tools that a model calls without discovering first
- Log a warning when auto-discovery happens (observability)
- Maintain the lazy loading optimization for models that follow the protocol

**Non-Goals:**
- Removing the `discover_tools` tool or the catalog system
- Auto-enabling tools that don't exist on any connected server (those should still fail)
- Changing the retry/error handling logic in `main.py`

## Decisions

### Decision: Auto-enable in the tool filter

Modify `create_tool_filter()` so the returned filter checks `all_known_tools` when a tool is not in `enabled_tools`. If the tool exists in `all_known_tools`, auto-add it to `enabled_tools` and return `True`.

**Why:** The filter already has access to the `ToolVisibilityContext` via `RunContextWrapper`, which contains both `enabled_tools` and `all_known_tools`. This is the natural interception point — no changes needed anywhere else.

**Alternative considered:** Catching `ModelBehaviorError` in the retry loop and auto-discovering before retry. Rejected because: (a) the error message doesn't always include the tool name in a parseable format, (b) it requires changes to the retry logic, and (c) it still wastes one full agent run.

### Decision: Warning-level log, not info

Log at WARNING level when auto-discovery happens. This makes it visible in dashboards without being noisy, and signals that the model isn't following the protocol optimally.

## Risks / Trade-offs

- **Trade-off: Models may learn to skip discovery entirely** → Acceptable. The lazy loading optimization saves prompt tokens but isn't required for correctness. Models that skip it just load all tool schemas they use, which is the non-lazy default behavior anyway.
- **Risk: Filter is called per-tool per-turn** → The `all_known_tools` lookup is an O(1) set check, so negligible performance impact. The warning log only fires once per tool (subsequent calls find it in `enabled_tools`).
