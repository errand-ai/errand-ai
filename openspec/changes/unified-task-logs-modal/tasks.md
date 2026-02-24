## 1. TaskLogModal: Add static logs mode

- [x] 1.1 Change `TaskLogModal` props: make `taskId` optional, add optional `runnerLogs: string` prop
- [x] 1.2 Move `parseRunnerLogs` function from `TaskEditModal` into `TaskLogModal` (same JSONL parsing logic with tool_result append and collapse defaults)
- [x] 1.3 Add static-mode logic in `onMounted`: if `runnerLogs` is provided, parse into `events`; otherwise connect WebSocket as before
- [x] 1.4 Update header text: show "Task Logs: {title}" when in static mode, keep "Live Logs: {title}" for WebSocket mode
- [x] 1.5 Hide "Waiting for logs..." message in static mode (events are immediately available)
- [x] 1.6 Hide "Task finished" indicator in static mode (task is already complete)

## 2. TaskCard: Unify logs button visibility

- [x] 2.1 Update `showLogButton` computed: return `true` when `running` OR when `(review|completed|scheduled) && runner_logs` is truthy
- [x] 2.2 Keep `showOutputButton` computed and the "View output" eye-icon button for `task.output` unchanged; only unify runner-logs viewing by routing runner logs through the unified `TaskLogModal`

## 3. KanbanBoard: Route logs to unified modal

- [x] 3.1 Update `onViewLogs` handler: pass `runnerLogs` prop to `TaskLogModal` when the task has `runner_logs` and is not `running`; pass `taskId` when the task is `running`
- [x] 3.2 Update `TaskLogModal` binding in template: conditionally bind `:task-id` and `:runner-logs` based on task status

## 4. TaskEditModal: Remove runner logs section

- [x] 4.1 Remove the `TaskEventLog` import and `TaskEvent` type import from `TaskEditModal`
- [x] 4.2 Remove the `lineCount` helper function and `parseRunnerLogs` function
- [x] 4.3 Remove the `parsedRunnerEvents` computed property
- [x] 4.4 Remove the runner logs template section (the `v-if="task.runner_logs"` block with "Task Runner Logs" heading and `TaskEventLog` component)

## 5. Tests

- [x] 5.1 Update `TaskLogModal` tests: add tests for static mode (renders parsed events from `runnerLogs` prop, no WebSocket connection, correct header text, no waiting message, no finished indicator)
- [x] 5.2 Update `TaskCard` tests: verify logs button shows for completed/review tasks with `runner_logs`, hidden for completed tasks without `runner_logs`
- [x] 5.3 Update `TaskEditModal` tests: remove tests for runner logs rendering (scenarios for "Runner logs displayed with rich rendering", "Runner logs fallback", "Runner logs hidden when absent", "Runner logs scrollable", "Runner logs visible in read-only mode")
- [x] 5.4 Update `KanbanBoard` tests: verify `TaskLogModal` receives `runnerLogs` prop for completed tasks and `taskId` for running tasks
- [x] 5.5 Run full frontend test suite and fix any failures
