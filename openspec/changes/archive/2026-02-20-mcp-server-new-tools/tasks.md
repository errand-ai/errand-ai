## 1. task_logs tool

- [x] 1.1 Add `task_logs` tool function to `backend/mcp_server.py` — accepts `task_id` (string), queries task by UUID, returns `runner_logs` content or appropriate error/empty message
- [x] 1.2 Add backend tests for `task_logs` — covers: task with logs, task with no logs, non-existent task

## 2. schedule_task tool

- [x] 2.1 Add `schedule_task` tool function to `backend/mcp_server.py` — accepts `description`, `execute_at` (required), `repeat_interval` (optional), `repeat_until` (optional); uses `generate_title()` for title but sets category from parameters; creates task with `status="scheduled"`, `created_by="mcp"`; publishes `task_created` event
- [x] 2.2 Add backend tests for `schedule_task` — covers: scheduled task, repeating task, repeating with end date, invalid datetime formats, short description (no LLM), long description (LLM title generation)

## 3. Spec updates

- [x] 3.1 Update `mcp-server-endpoint` spec tool discovery scenario to include `task_logs` and `schedule_task` in the expected tools list (delta spec already prepared — will be synced at archive time)
