## Context

The edit task modal (TaskEditModal.vue) currently has read-only modes for `running` status and `viewer` role users, but completed tasks remain fully editable. The runner logs are displayed as a plain `<pre>` block.

The TaskLogModal (live log viewer) renders structured events (thinking, reasoning, tool_call, tool_result, error, raw, agent_start, agent_end) with rich visual formatting — collapsible cards, styled blocks, etc. The `runner_logs` field in the database stores the same structured events as newline-delimited JSON (one event per line from the task runner's stderr).

## Goals / Non-Goals

**Goals:**
- Make completed tasks read-only in the edit modal (same pattern as running tasks)
- Extract the structured event rendering from TaskLogModal into a reusable component
- Use the shared renderer in both TaskLogModal (live events) and TaskEditModal (stored runner_logs)
- Parse `runner_logs` text into the same event structure used by the live view

**Non-Goals:**
- Changing the runner_logs storage format (it's already newline-delimited JSON events)
- Adding editing capabilities to completed tasks through any other UI path
- Modifying the TaskLogModal's WebSocket connection or live streaming behaviour

## Decisions

### Decision 1: Extract event rendering into TaskEventLog component

**Choice:** Create a new `TaskEventLog.vue` component that accepts an array of parsed events and renders them with the rich formatting currently in TaskLogModal. TaskLogModal passes live events to it; TaskEditModal parses `runner_logs` and passes the parsed array.

**Why:** Avoids duplicating the rendering logic. The TaskLogModal manages WebSocket connection and live event accumulation; the new component handles only rendering. TaskEditModal needs only rendering from static data.

**Alternatives considered:**
- Embed TaskLogModal in read-only/static mode: Too coupled to WebSocket lifecycle; would need significant refactoring to work without a connection
- Duplicate rendering in TaskEditModal: Maintenance burden, inconsistent UX over time

### Decision 2: Completed tasks use same read-only pattern as running tasks

**Choice:** Extend the existing `isReadOnly` computed property to include `status === 'completed'` alongside `running` and viewer role checks. All field disabling and button hiding flows through this single flag.

**Why:** The pattern already exists and is well-tested. Completed tasks have the same requirements — no editing, no save/delete, only close.

### Decision 3: Runner logs section uses TaskEventLog instead of `<pre>`

**Choice:** Replace the plain `<pre>` block for runner_logs with the TaskEventLog component. Parse `runner_logs` (newline-delimited JSON) into an event array and pass it to the renderer. Increase `max-h-48` to `max-h-96` to give the richer rendering more room.

**Why:** The structured events contain tool calls, thinking, reasoning, etc. that are much more readable with the rich rendering. The `<pre>` block loses all this structure.

**Fallback:** If a line in `runner_logs` is not valid JSON, render it as a `raw` event (same as the live view does for non-JSON stderr lines).

## Risks / Trade-offs

- **Larger component tree in edit modal**: TaskEventLog adds rendering complexity → Acceptable; only renders when runner_logs exist
- **Parsing overhead for large logs**: Parsing many lines of JSON on modal open → Mitigated by `max-h-96` with scroll; parsing is fast for typical log sizes
