# Proposal: Improve Task Log Rendering

## Problem

The Task Logs popup window renders log events in the order they arrive from the streaming API, which produces a confusing reading experience:

1. **Ordering**: `tool_call` events appear before the `thinking` message that motivated them. The model logically thinks first ("I'll research how to run Playwright MCP servers..."), then calls tools (`web_search`), but the API streams tool calls before text output.

2. **HTTP noise**: Raw `INFO HTTP Request: POST ...` lines from Python's httpx library clutter the log view. These are the transport layer for tool calls and LLM API calls but appear as disconnected raw text.

3. **MCP connection spam**: ~40 raw log lines for MCP server initialization (connect, negotiate, list tools) dominate the early log output.

## Proposed Solution

### Backend (task-runner)

- **Suppress httpx INFO logging** — eliminates HTTP request noise at the source
- **Emit structured `llm_turn_start` event** — marks each LLM turn with a `turn_id` and model name, replacing the raw `POST .../chat/completions` line
- **Add `turn_id` to all streaming events** — enables frontend turn-based grouping
- **Add `duration_ms` to `tool_result` events** — captures tool execution timing via `on_tool_start`/`on_tool_end` hooks
- **Emit structured `mcp_connected` event** — replaces the flood of raw MCP connection log lines with a single summary event

### Frontend (TaskLogViewer in errand-component-library)

- **Turn-based grouping** — group events by `turn_id`, render thinking before tool_calls within each turn
- **Thinking placeholder** — in live mode, show a "Thinking..." placeholder when `llm_turn_start` arrives; replace with actual text when `thinking` event arrives
- **Turn separator** — render `llm_turn_start` as a subtle horizontal rule with model name
- **Tool status indicators** — show green check / red cross / spinner on tool_call headers based on result status
- **Tool duration** — show execution time from `duration_ms` on tool_call entries
- **MCP connection summary** — render `mcp_connected` as a collapsible "MCP servers connected (N)" line
- **Backward compatibility** — gracefully handle logs without `turn_id` (existing stored `runner_logs`) by falling back to current flat rendering

## Scope

- **In scope**: task-runner event emission, TaskLogViewer rendering
- **Out of scope**: Log storage format changes, API endpoint changes, other raw `logging.info()` lines (keep for now, revisit later)

## Risks

- **Two-repo coordination**: Backend changes (errand) and frontend changes (errand-component-library) need coordinated releases. Deploy backend first since frontend ignores unknown fields.
- **Streaming UX**: The "Thinking..." placeholder approach depends on `llm_turn_start` always preceding tool_call events. If the SDK hook ordering changes, the placeholder may flash incorrectly.
