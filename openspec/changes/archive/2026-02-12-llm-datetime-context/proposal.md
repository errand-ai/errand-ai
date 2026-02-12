## Why

The LLM task classifier has no concept of the current date and time. When users create tasks with relative time references — "in 10 minutes", "at the end of the working day", "every 30 minutes starting now" — the LLM cannot resolve these to concrete `execute_at` datetimes because neither the system prompt nor the user message includes the current timestamp. This causes scheduled and repeating tasks to receive incorrect or null `execute_at` values, which breaks the task scheduler's ability to pick them up at the right time.

## What Changes

- Include the current UTC datetime in the LLM system prompt so the model can resolve relative time references ("in 10 minutes", "tomorrow", "end of day") to concrete ISO 8601 timestamps
- Include the user's timezone context (defaulting to UTC) so the LLM can correctly interpret phrases like "at 5pm" or "end of the working day" relative to the user's local time
- Add a `timezone` user setting so users can configure their local timezone (e.g. `Europe/London`, `America/New_York`)
- For `immediate` category tasks, the backend sets `execute_at` to the current server time directly rather than relying on the LLM to guess "now"

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `llm-integration`: System prompt updated to include current UTC datetime and user timezone; `generate_title` function accepts and passes datetime context
- `task-categorisation`: `execute_at` for `immediate` tasks set by the backend (not the LLM); new `timezone` setting added

## Impact

- **Backend**: `llm.py` — system prompt modified to include datetime context; `generate_title` signature gains a datetime parameter
- **Backend**: `main.py` — passes current datetime to `generate_title`; sets `execute_at = now()` for immediate tasks post-LLM-call
- **Backend**: `models.py` — no changes (Setting model already supports arbitrary key/value pairs)
- **Backend tests**: `test_llm.py` — tests updated to verify datetime context in system prompt; mock assertions adjusted
- **Frontend**: Settings page may need a timezone selector (if not already present)
- **No database migration** — uses existing `settings` table for the timezone key
- **No API changes** — task creation endpoint unchanged
