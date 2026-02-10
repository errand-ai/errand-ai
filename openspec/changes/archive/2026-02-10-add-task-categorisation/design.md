## Context

Tasks are currently created with status `new` and require manual triage to move them to the appropriate column. The LLM is already used during task creation to generate titles from long descriptions. We can extend this LLM call to also categorise tasks and extract timing information, enabling automatic routing to the correct column.

The existing task model has `id`, `title`, `description`, `status`, `created_at`, `updated_at`, and tag associations. The LLM integration lives in `backend/llm.py` and is called from `POST /api/tasks` in `backend/main.py`.

## Goals / Non-Goals

**Goals:**
- Automatically categorise tasks as immediate, scheduled, or repeating using the LLM
- Extract execution timing from natural language descriptions (e.g. "at 5pm", "in 15 minutes", "every day")
- Auto-route tasks to the correct column after creation based on category
- Display execution time on scheduled task cards
- Allow manual editing of category, execute_at, and repeat_interval via the edit modal

**Non-Goals:**
- Actually executing or triggering tasks at the scheduled time (no scheduler/cron — that's future work)
- Recurring task rescheduling logic (the `repeat_interval` is stored but not acted on automatically)
- Natural language parsing on the backend independent of the LLM — we rely on the LLM for all timing extraction
- Calendar or timeline views for scheduled tasks

## Decisions

### Decision 1: Single LLM call for title + categorisation

Extend the existing LLM call to return structured JSON with title, category, and timing in one request rather than making separate calls for title generation and categorisation.

**Rationale:** Reduces latency and cost. The LLM already reads the full description for title generation — it can categorise simultaneously.

**Alternative considered:** Two separate LLM calls (one for title, one for categorisation). Rejected because it doubles latency and cost with no benefit.

**Implementation:** The LLM prompt will request a JSON response with fields: `title` (string), `category` (immediate|scheduled|repeating), `execute_at` (ISO 8601 datetime or null), `repeat_interval` (string or null), `repeat_until` (ISO 8601 datetime or null). The response will be parsed with `json.loads()`. If JSON parsing fails, fall back to using the raw response as the title with category `immediate`.

### Decision 2: Category as a text column with enum validation

Store `category` as a text column validated at the application level (like `status`), not a PostgreSQL enum.

**Rationale:** Consistent with how `status` is implemented. Application-level validation is easier to extend without migrations.

**Alternative considered:** PostgreSQL enum type. Rejected for consistency with existing patterns and migration simplicity.

**Valid values:** `immediate`, `scheduled`, `repeating`

### Decision 3: execute_at as timestamptz, repeat_interval as text

- `execute_at`: `TIMESTAMP WITH TIME ZONE`, nullable. Set to `now()` for immediate tasks, a future time for scheduled tasks, and the next execution time for repeating tasks.
- `repeat_interval`: `TEXT`, nullable. Stores either a simple interval string (e.g. `"15m"`, `"1h"`, `"1d"`, `"1w"`) or a crontab expression (e.g. `"0 9 * * MON-FRI"`, `"*/30 * * * *"`). Only populated for repeating tasks.
- `repeat_until`: `TIMESTAMP WITH TIME ZONE`, nullable. Stores when a repeating task should stop recurring. Only meaningful for repeating tasks. If null, the task repeats indefinitely.

**Rationale:** `timestamptz` is the standard for point-in-time values. Text interval is simpler than PostgreSQL `INTERVAL` type and easier to display in the frontend. Supporting both simple intervals and crontab expressions gives power users flexibility while keeping simple cases easy. The LLM extracts these values from natural language, so a flexible text format works well. `repeat_until` is separate from `execute_at` because they serve different purposes — when to run next vs when to stop recurring.

**Alternative considered:** PostgreSQL `INTERVAL` for repeat_interval. Rejected because we're not doing arithmetic on it yet (no scheduler), and text is simpler to round-trip through JSON. Crontab-only was considered but simple intervals like "1h" are more natural for basic use cases.

### Decision 4: Auto-routing logic in POST /api/tasks

After the LLM categorises the task, the backend applies routing rules before saving:
1. If the task has a "Needs Info" tag → stay in `new` (no auto-route)
2. If category is `immediate` → set status to `pending`
3. If category is `scheduled` or `repeating` → set status to `scheduled`

This logic runs after both the LLM call and the "Needs Info" tag application for short inputs. Short inputs (≤5 words) always get "Needs Info" and stay in `new`.

**Rationale:** Routing at creation time avoids an extra PATCH call and gives immediate visual feedback on the board.

### Decision 4b: Auto-promotion from "New" on edit

When a task in the "New" column with a "Needs Info" tag is updated via PATCH, and the update includes both:
1. A non-empty `description` (the user has provided more detail), AND
2. An `execute_at` or `repeat_interval` value (scheduling information is present)

Then the backend SHALL:
1. Remove the "Needs Info" tag from the task
2. Set the task's status to `scheduled`

This allows tasks that initially lacked detail (short input, LLM failure) to be promoted to the correct column once the user fills in the missing information via the edit modal.

**Rationale:** Tasks stuck in "New" with "Needs Info" are there because they lacked sufficient context. Once the user provides both a description and scheduling info, the task has enough context to be routed. Removing "Needs Info" and moving to "scheduled" mirrors what would have happened at creation time if the LLM had succeeded.

**Guard rails:** This only fires when status is `new` AND the "Needs Info" tag is present. If the user has already manually moved the task elsewhere, this logic does not apply.

### Decision 5: Fallback behaviour when LLM fails or is unavailable

When the LLM call fails, times out, or the client is not configured:
- Category defaults to `immediate`
- `execute_at` defaults to `now()`
- `repeat_interval` defaults to null
- The "Needs Info" tag is applied (existing behaviour)
- Task stays in `new` (because "Needs Info" tag prevents auto-routing)

**Rationale:** Preserves existing fallback behaviour. The "Needs Info" tag already signals that a task needs manual review.

### Decision 6: Frontend display of execute_at

Task cards in the Scheduled column will display the `execute_at` value as a relative time string (e.g. "in 15 minutes", "at 5:00 PM today", "tomorrow at 9:00 AM") below the title and above the tags. Cards in other columns will not display execute_at.

**Rationale:** Relative time is more useful than absolute timestamps for quick scanning. Only showing in Scheduled avoids clutter on other columns.

### Decision 7: Delete task endpoint and UI

Add `DELETE /api/tasks/{id}` to the backend. The endpoint deletes the task and its tag associations, publishes a `task_deleted` event to Valkey, and returns HTTP 204.

On the frontend, deletion is available in two places:
1. A "Delete" button in the task edit modal (below Save/Cancel) — styled as a danger action
2. A small delete icon (trash) on each task card — for quick deletion without opening the modal

Both triggers show a confirmation dialog before proceeding. On confirmation, the frontend calls `DELETE /api/tasks/{id}` and removes the task from the local store.

**Rationale:** Users need to be able to remove tasks they no longer need. Having two entry points (card icon and modal button) reduces friction. Confirmation prevents accidental deletion.

### Decision 8: User-friendly datetime picker for execute_at

The execute_at field in the edit modal uses a native `<input type="datetime-local">` element. The value is converted between the local time zone and UTC (ISO 8601) for API communication.

**Rationale:** Native datetime-local inputs are well-supported in modern browsers and provide a built-in date/time picker without third-party dependencies. They handle date validation automatically.

**Alternative considered:** A third-party date picker library. Rejected to avoid adding dependencies for a feature that native inputs handle adequately.

### Decision 9: Guided repeat_interval input with crontab support

The repeat_interval field in the edit modal includes:
1. A text input for entering the interval value
2. Helper text below the input showing accepted formats: simple intervals (`15m`, `1h`, `1d`, `1w`) and crontab expressions (`0 9 * * MON-FRI`)
3. Quick-select buttons for common intervals (15m, 1h, 1d, 1w) that populate the input

**Rationale:** Users unfamiliar with crontab need guidance. Quick-select buttons cover the most common cases. Power users can type crontab expressions directly.

**Alternative considered:** A structured crontab builder UI. Rejected as over-engineered for this stage — a guided text input with examples is sufficient.

### Decision 10: repeat_until field and datetime picker

The `repeat_until` field stores an optional end date for repeating tasks. It uses the same `<input type="datetime-local">` approach as `execute_at`. The LLM prompt includes `repeat_until` in its JSON schema so it can extract end dates from natural language (e.g. "every day until March 1st"). If no end date is mentioned, the field is null (repeat indefinitely).

In the edit modal, `repeat_until` appears below `repeat_interval` and is only visible when category is "repeating". The label is "Repeat until" with a datetime picker.

**Rationale:** Users need to be able to set an expiry on recurring tasks. Using the same datetime-local input pattern as execute_at keeps the UI consistent.

## Risks / Trade-offs

- **LLM categorisation accuracy** → The LLM may miscategorise tasks or extract incorrect timing. Mitigation: users can manually edit category and timing in the edit modal; "Needs Info" fallback prevents auto-routing on failure.
- **JSON parsing fragility** → The LLM may not always return valid JSON. Mitigation: fall back to treating the response as a plain title with `immediate` category if JSON parsing fails.
- **Time zone ambiguity** → Users may say "at 5pm" without specifying a time zone. Mitigation: the LLM will be instructed to interpret times relative to UTC. Users can adjust via the edit modal.
- **repeat_interval not acted on** → Storing the interval without a scheduler may confuse users who expect automatic rescheduling. Mitigation: this is documented as future work; the UI shows the interval as informational.

## Migration Plan

1. Create Alembic migration adding `category` (text, nullable, default `immediate`), `execute_at` (timestamptz, nullable), `repeat_interval` (text, nullable), and `repeat_until` (timestamptz, nullable) to the `tasks` table
2. Existing tasks get `category = 'immediate'` via the default, null for execute_at, repeat_interval, and repeat_until
3. Migration is additive — backward-compatible with existing backend replicas during rollout
4. Rollback: downgrade migration drops the four columns
