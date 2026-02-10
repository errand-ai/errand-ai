## Why

Tasks created today all start in the "New" column regardless of their nature. Users must manually triage every task to determine when it should run. By using the LLM to automatically categorise tasks at creation time -- as immediate, scheduled, or repeating -- we can route them to the correct column and reduce manual triage effort.

## What Changes

- Add a `category` field to the task model with values: `immediate`, `scheduled`, `repeating`
- Add an `execute_at` field (timestamptz, nullable) to store when the task should next run
- Add a `repeat_interval` field (text, nullable) to store the repeat interval for repeating tasks — supports simple intervals (`15m`, `1h`, `1d`) and crontab expressions (`0 9 * * MON-FRI`)
- Add a `repeat_until` field (timestamptz, nullable) to store when a repeating task should stop recurring
- Extend the LLM title generation step to also categorise the task and extract timing information from the description (including repeat_until if mentioned)
- Auto-route tasks after creation: if the task does not have a "Needs Info" tag, move `immediate` tasks to `pending` and `scheduled`/`repeating` tasks to `scheduled`
- When editing a task in the "New" column that has a "Needs Info" tag: if the user adds scheduling fields (execute_at or repeat_interval) and updates the description, automatically remove the "Needs Info" tag and move the task to `scheduled`
- Display `execute_at` on task cards in the Scheduled column
- Add an Alembic migration for the new columns
- Include `category`, `execute_at`, and `repeat_interval` in task API responses and allow them in PATCH requests
- Show category, execute_at, repeat_interval, and repeat_until fields in the task edit modal with user-friendly inputs (datetime pickers for execute_at and repeat_until, guided input with format hints for repeat_interval)
- Add `DELETE /api/tasks/{id}` endpoint to remove tasks
- Add delete button with confirmation dialog in the task edit modal
- Add delete icon on task cards for quick deletion with confirmation

## Capabilities

### New Capabilities
- `task-categorisation`: LLM-based categorisation of tasks into immediate/scheduled/repeating, timing extraction, and auto-routing logic

### Modified Capabilities
- `task-api`: Add `category`, `execute_at`, `repeat_interval`, `repeat_until` fields to task responses and PATCH; add `DELETE /api/tasks/{id}` endpoint; auto-route tasks after creation based on category; auto-promote tasks from "New" when scheduling fields are added via PATCH
- `kanban-frontend`: Display `execute_at` on cards in the Scheduled column; add delete icon on task cards with confirmation
- `task-edit-modal`: Show and allow editing of `category`, `execute_at` (datetime picker), `repeat_interval` (guided input with crontab support), and `repeat_until` (datetime picker) fields; add delete button with confirmation dialog
- `llm-integration`: Extend LLM prompt to categorise tasks and extract timing alongside title generation

## Impact

- **Database**: New Alembic migration adding 4 columns to `tasks` table (`category`, `execute_at`, `repeat_interval`, `repeat_until`)
- **Backend**: `models.py` (new columns), `main.py` (task creation routing, PATCH support), `llm.py` (extended prompt for categorisation)
- **Frontend**: `TaskCard.vue` (show execute_at in Scheduled), `TaskEditModal.vue` (new fields), `stores/tasks.ts` (updated type)
- **API**: Task responses gain 3 new fields; PATCH accepts them; POST auto-routes based on category; new DELETE endpoint
- **Helm**: No changes expected (no new env vars or services)
