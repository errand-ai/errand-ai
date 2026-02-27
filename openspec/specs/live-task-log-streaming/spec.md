## Purpose

Live log viewer button on task cards and WebSocket-based real-time log streaming from running task runners.

## Requirements

### Requirement: Live log viewer button on running task cards

The frontend SHALL display a "View Logs" button (terminal/code icon) on task cards when the task is in the `running` status OR when the task is in `review`, `completed`, or `scheduled` status and has a non-null `runner_logs` field. The button SHALL emit a `view-logs` event when clicked.

#### Scenario: Button visible on running task

- **WHEN** a task card is rendered with status `running`
- **THEN** a "View Logs" button (terminal/code icon) is visible on the card

#### Scenario: Button visible on completed task with runner_logs

- **WHEN** a task card is rendered with status `completed` and the task has a non-null `runner_logs` field
- **THEN** a "View Logs" button (terminal/code icon) is visible on the card

#### Scenario: Button visible on review task with runner_logs

- **WHEN** a task card is rendered with status `review` and the task has a non-null `runner_logs` field
- **THEN** a "View Logs" button (terminal/code icon) is visible on the card

#### Scenario: Button visible on scheduled task with runner_logs

- **WHEN** a task card is rendered with status `scheduled` and the task has a non-null `runner_logs` field
- **THEN** a "View Logs" button (terminal/code icon) is visible on the card

#### Scenario: Button hidden on completed task without runner_logs

- **WHEN** a task card is rendered with status `completed` and the task has a null `runner_logs` field
- **THEN** the "View Logs" button is not visible

#### Scenario: Button hidden on pending task

- **WHEN** a task card is rendered with status `pending`
- **THEN** the "View Logs" button is not visible

#### Scenario: Button click emits event

- **WHEN** the user clicks the "View Logs" button on a task card
- **THEN** the card emits a `view-logs` event with no payload

### Requirement: Live log viewer modal

The frontend SHALL provide a `TaskLogModal` component that displays task runner events. The modal SHALL support two modes:

1. **Live mode**: When mounted with a `taskId` prop and no `runnerLogs` prop, the modal SHALL open a WebSocket connection to `/api/ws/tasks/{task_id}/logs` and stream events in real time. The header SHALL display "Live Logs: {title}".
2. **Static mode**: When mounted with a `runnerLogs` prop (newline-delimited JSON string), the modal SHALL parse the string into structured events and render them immediately without a WebSocket connection. The header SHALL display "Task Logs: {title}".

In both modes, the modal SHALL render events using the `TaskEventLog` component in a scrollable dark-themed container.

#### Scenario: Modal displays streaming log lines

- **WHEN** the log viewer modal is opened for a running task (live mode) and the WebSocket receives `{"event": "task_event", "type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}}`
- **THEN** the modal appends a tool_call event to the displayed log output

#### Scenario: Auto-scroll follows new output

- **WHEN** the log viewer is open in live mode and new log lines arrive
- **THEN** the log display auto-scrolls to show the latest line

#### Scenario: Stream ends gracefully

- **WHEN** the WebSocket receives `{"event": "task_log_end"}`
- **THEN** the modal displays a "Task finished" indicator and stops waiting for new lines

#### Scenario: Modal close disconnects WebSocket

- **WHEN** the user closes the log viewer modal in live mode (via Close button, Escape, or backdrop click)
- **THEN** the WebSocket connection is closed

#### Scenario: Empty log state in live mode

- **WHEN** the log viewer modal opens in live mode and no log lines have been received yet
- **THEN** the modal displays "Waiting for logs..."

#### Scenario: Modal uses terminal-style presentation

- **WHEN** the log viewer modal is displaying log lines
- **THEN** the output area uses a dark background (`bg-gray-900`) with light text, presented in a scrollable container

#### Scenario: Static mode renders runner_logs

- **WHEN** the log viewer modal is opened with a `runnerLogs` prop containing newline-delimited JSON events
- **THEN** the modal parses the JSONL string into structured events and renders them using `TaskEventLog`

#### Scenario: Static mode header shows "Task Logs"

- **WHEN** the log viewer modal is opened in static mode
- **THEN** the header displays "Task Logs: {title}" (not "Live Logs")

#### Scenario: Static mode does not connect WebSocket

- **WHEN** the log viewer modal is opened with a `runnerLogs` prop
- **THEN** no WebSocket connection is established

#### Scenario: Static mode does not show waiting message

- **WHEN** the log viewer modal opens in static mode with parsed events
- **THEN** the modal does not display "Waiting for logs..."

#### Scenario: Static mode does not show task finished indicator

- **WHEN** the log viewer modal is opened in static mode
- **THEN** the "Task finished" indicator is not displayed (the task is already complete)

#### Scenario: Static mode handles non-JSON lines

- **WHEN** the `runnerLogs` string contains lines that are not valid JSON
- **THEN** those lines are rendered as `raw` events (plain monospace text)

#### Scenario: Static mode tool_result appended to tool_call

- **WHEN** the `runnerLogs` string contains a `tool_call` event followed by a `tool_result` event with a matching tool name
- **THEN** the tool_result is appended to the preceding tool_call event card rather than rendered as a separate event
