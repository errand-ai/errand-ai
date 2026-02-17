## 1. Extract Shared Event Renderer

- [x] 1.1 Create `TaskEventLog.vue` component that accepts an `events` array prop and renders structured events with the same rich formatting currently in TaskLogModal (thinking, reasoning, tool_call, tool_result, agent_start, agent_end, error, raw)
- [x] 1.2 Refactor `TaskLogModal.vue` to use `TaskEventLog` for rendering, keeping only the WebSocket connection, event accumulation, and auto-scroll logic in TaskLogModal

## 2. Edit Modal: Read-Only Mode for Completed Tasks

- [x] 2.1 Extend the `isReadOnly` computed property in `TaskEditModal.vue` to include `status === 'completed'` alongside the existing `running` and viewer role checks
- [x] 2.2 Verify that the read-only mode skips the dirty check on modal dismissal (backdrop click / Escape closes immediately for completed tasks)

## 3. Edit Modal: Rich Runner Logs

- [x] 3.1 Add a `parseRunnerLogs(text)` function that splits `runner_logs` by newlines, parses each line as JSON into `{type, data}` events, and falls back to `{type: 'raw', data: {line: text}}` for non-JSON lines
- [x] 3.2 Replace the plain `<pre>` runner logs block in `TaskEditModal.vue` with the `TaskEventLog` component, passing parsed events
- [x] 3.3 Update the runner logs container height from `max-h-48` to `max-h-96`

## 4. Frontend Tests

- [x] 4.1 Add tests for `TaskEventLog.vue`: verify each event type renders with correct styling (thinking italic, reasoning border, tool_call collapsible, error red, raw monospace)
- [x] 4.2 Update `TaskLogModal` tests to verify it delegates rendering to TaskEventLog
- [x] 4.3 Add test: completed task opens edit modal in read-only mode (fields disabled, Save/Delete hidden)
- [x] 4.4 Add test: edit modal parses runner_logs into structured events and renders via TaskEventLog
- [x] 4.5 Add test: non-JSON runner_logs lines render as raw events
- [x] 4.6 Verify existing TaskEditModal tests still pass
