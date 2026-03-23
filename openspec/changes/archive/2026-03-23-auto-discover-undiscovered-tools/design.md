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

### Decision: Catch ModelBehaviorError in the retry loop

Add a specific `except ModelBehaviorError` handler in the agent retry loop that parses the tool name from the error message ("Tool X not found in agent Y"), auto-enables it in the `ToolVisibilityContext`, and retries.

**Why:** The tool filter is called when the SDK lists tools for the LLM (every turn), not just when a tool is called. Auto-enabling in the filter causes ALL known tools to be enabled at once, defeating lazy loading entirely and bloating the LLM context with ~45 tool schemas.

**Alternative considered (and reverted):** Auto-enabling in the `tool_filter` function. This caused all tools to auto-enable on the first turn of any retry, defeating the lazy loading optimization completely. The filter cannot distinguish "listing tools" from "calling a tool."

### Decision: Warning-level log, not info

Log at WARNING level when auto-discovery happens. This makes it visible in dashboards without being noisy, and signals that the model isn't following the protocol optimally.

## Risks / Trade-offs

- **Trade-off: Costs one failed agent run per undiscovered tool** → Acceptable. The retry catches the error and auto-enables only the specific tool the model tried to use, preserving lazy loading for all other tools. This is much better than enabling all tools at once.
- **Risk: Error message format changes** → The regex `r"Tool (\S+) not found in agent"` depends on the OpenAI Agents SDK error format. If it changes, the fallback is the existing behavior (fail and exit).
