## ADDED Requirements

### Requirement: Task category field
Each task SHALL have a `category` field with valid values: `immediate`, `scheduled`, `repeating`. The category indicates whether the task should be executed now, at a specific future time, or on a recurring basis. The default category for new tasks SHALL be `immediate`.

#### Scenario: Task created with immediate category
- **WHEN** the LLM categorises a task as immediate
- **THEN** the task's `category` field is set to `immediate`

#### Scenario: Task created with scheduled category
- **WHEN** the LLM categorises a task as scheduled
- **THEN** the task's `category` field is set to `scheduled`

#### Scenario: Task created with repeating category
- **WHEN** the LLM categorises a task as repeating
- **THEN** the task's `category` field is set to `repeating`

#### Scenario: Invalid category rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"category": "invalid"}`
- **THEN** the backend returns HTTP 422 with a validation error listing the valid categories

### Requirement: Task execute_at field
Each task SHALL have an `execute_at` field (timestamptz, nullable) storing when the task should next be executed. For `immediate` tasks, `execute_at` SHALL be set to the current server time (`datetime.now(timezone.utc)`) by the backend at creation, regardless of the LLM response. For `scheduled` and `repeating` tasks, `execute_at` SHALL be set to the time extracted by the LLM from the task description. If no time can be extracted, `execute_at` SHALL be null.

#### Scenario: Immediate task gets current time from backend
- **WHEN** a task is created with category `immediate`
- **THEN** `execute_at` is set to the current server time by the backend, not by the LLM response

#### Scenario: Scheduled task gets future time
- **WHEN** a task is created with description "Send the report at 5pm" and the LLM extracts a future time
- **THEN** `execute_at` is set to the extracted datetime

#### Scenario: Repeating task gets first execution time
- **WHEN** a task is created with description "Every 30 minutes, check the logs" and the LLM extracts a start time
- **THEN** `execute_at` is set to the extracted datetime for the first iteration

#### Scenario: No time extracted
- **WHEN** the LLM cannot extract a specific time from the description
- **THEN** `execute_at` is null

### Requirement: Task repeat_interval field
Each task SHALL have a `repeat_interval` field (text, nullable) storing the recurrence interval for repeating tasks. The interval SHALL be either a simple duration string (e.g. `"15m"`, `"1h"`, `"1d"`, `"1w"`) or a crontab expression (e.g. `"0 9 * * MON-FRI"`, `"*/30 * * * *"`). For non-repeating tasks, `repeat_interval` SHALL be null.

#### Scenario: Repeating task with simple interval
- **WHEN** a task is created with description "Check server health every 15 minutes" and the LLM categorises it as repeating
- **THEN** `repeat_interval` is set to `"15m"` (or similar simple interval)

#### Scenario: Repeating task with crontab expression
- **WHEN** a task is created with description "Run the backup every weekday at 9am" and the LLM categorises it as repeating
- **THEN** `repeat_interval` is set to a crontab expression like `"0 9 * * MON-FRI"`

#### Scenario: Non-repeating task has null interval
- **WHEN** a task is created with category `immediate` or `scheduled`
- **THEN** `repeat_interval` is null

### Requirement: Task repeat_until field
Each task SHALL have a `repeat_until` field (timestamptz, nullable) storing when a repeating task should stop recurring. For non-repeating tasks, `repeat_until` SHALL be null. If the LLM extracts an end date from the description, it SHALL populate this field. If no end date is mentioned, `repeat_until` SHALL be null (repeat indefinitely).

#### Scenario: Repeating task with end date
- **WHEN** a task is created with description "Run the daily report every day until March 1st" and the LLM extracts an end date
- **THEN** `repeat_until` is set to the extracted datetime (e.g. 2026-03-01T00:00:00Z)

#### Scenario: Repeating task without end date
- **WHEN** a task is created with description "Check server health every 15 minutes" and no end date is mentioned
- **THEN** `repeat_until` is null

#### Scenario: Non-repeating task has null repeat_until
- **WHEN** a task is created with category `immediate` or `scheduled`
- **THEN** `repeat_until` is null

### Requirement: Auto-routing after task creation
After a task is created and categorised, the backend SHALL automatically set the task's status based on its category and tags. If the task has a "Needs Info" tag, the task SHALL remain in status `new` regardless of category. Otherwise: `immediate` tasks SHALL be moved to `pending`, and `scheduled` or `repeating` tasks SHALL be moved to `scheduled`.

#### Scenario: Immediate task without Needs Info moves to pending
- **WHEN** a task is created with category `immediate` and no "Needs Info" tag
- **THEN** the task's status is set to `pending`

#### Scenario: Scheduled task without Needs Info moves to scheduled
- **WHEN** a task is created with category `scheduled` and no "Needs Info" tag
- **THEN** the task's status is set to `scheduled`

#### Scenario: Repeating task without Needs Info moves to scheduled
- **WHEN** a task is created with category `repeating` and no "Needs Info" tag
- **THEN** the task's status is set to `scheduled`

#### Scenario: Task with Needs Info stays in new
- **WHEN** a task is created with category `immediate` but has the "Needs Info" tag
- **THEN** the task's status remains `new`

#### Scenario: Short input stays in new
- **WHEN** a task is created with a short input (5 words or fewer)
- **THEN** the task gets the "Needs Info" tag and remains in status `new`

### Requirement: Auto-promotion from New on edit
When a task in the "New" column with a "Needs Info" tag is updated via `PATCH /api/tasks/{id}`, and the update includes a non-empty `description` AND an `execute_at` or `repeat_interval` value, the backend SHALL automatically remove the "Needs Info" tag and set the task's status to `scheduled`.

#### Scenario: Task promoted from New to Scheduled on edit
- **WHEN** a task has status `new` and the "Needs Info" tag, and a PATCH updates description to "Generate the quarterly financial report" and execute_at to "2026-02-15T17:00:00Z"
- **THEN** the "Needs Info" tag is removed, the task's status is set to `scheduled`, and the updated task is returned

#### Scenario: Task with description and repeat_interval promoted
- **WHEN** a task has status `new` and the "Needs Info" tag, and a PATCH updates description to "Check server health" and repeat_interval to "1h"
- **THEN** the "Needs Info" tag is removed and the task's status is set to `scheduled`

#### Scenario: Description alone does not trigger promotion
- **WHEN** a task has status `new` and the "Needs Info" tag, and a PATCH updates only the description (no execute_at or repeat_interval)
- **THEN** the "Needs Info" tag remains and the task stays in status `new`

#### Scenario: Scheduling fields alone do not trigger promotion
- **WHEN** a task has status `new` and the "Needs Info" tag, and a PATCH updates only execute_at (no description update)
- **THEN** the "Needs Info" tag remains and the task stays in status `new`

#### Scenario: Promotion only applies to tasks in New with Needs Info
- **WHEN** a task has status `running` (not `new`) and a PATCH updates description and execute_at
- **THEN** the auto-promotion logic does not apply; the task status is unchanged by this logic

### Requirement: Database migration for categorisation fields
An Alembic migration SHALL add four columns to the `tasks` table: `category` (text, nullable, default `immediate`), `execute_at` (timestamptz, nullable), `repeat_interval` (text, nullable), and `repeat_until` (timestamptz, nullable). Existing tasks SHALL receive `category = 'immediate'` via the column default.

#### Scenario: Migration adds columns
- **WHEN** the migration runs
- **THEN** the `tasks` table gains `category`, `execute_at`, `repeat_interval`, and `repeat_until` columns

#### Scenario: Existing tasks get default category
- **WHEN** the migration runs against a database with existing tasks
- **THEN** existing tasks have `category = 'immediate'`, `execute_at = NULL`, `repeat_interval = NULL`, and `repeat_until = NULL`

#### Scenario: Migration is reversible
- **WHEN** the migration is downgraded
- **THEN** the four columns are dropped

### Requirement: Timezone setting
The application SHALL support a `timezone` setting stored in the `settings` table with key `timezone`. The value SHALL be an IANA timezone name (e.g. `Europe/London`, `America/New_York`, `UTC`). If not configured, the default timezone SHALL be `UTC`. This setting is used by the LLM categorisation system to resolve local time references in task descriptions.

#### Scenario: Timezone setting saved
- **WHEN** an admin sends `PUT /api/settings` with `{"timezone": "Europe/London"}`
- **THEN** the timezone setting is stored and returned in subsequent `GET /api/settings` responses

#### Scenario: Default timezone when not set
- **WHEN** no timezone setting exists in the database
- **THEN** the system uses `UTC` as the default timezone

#### Scenario: Timezone used in LLM prompt
- **WHEN** a task is created and the timezone setting is `America/New_York`
- **THEN** the LLM system prompt includes `America/New_York` as the user's timezone

### Requirement: Timezone selector on settings page
The frontend settings page SHALL include a "Timezone" section with a `<select>` dropdown populated using the browser's `Intl.supportedValuesOf('timeZone')` API. The selected timezone SHALL be saved via `PUT /api/settings` with key `timezone` and loaded from `GET /api/settings` on page load. The default selection SHALL be `UTC` if no timezone setting is configured.

#### Scenario: Timezone selector displayed
- **WHEN** the settings page loads
- **THEN** a "Timezone" section is visible with a dropdown containing IANA timezone names

#### Scenario: Timezone populated from settings
- **WHEN** the settings page loads and the timezone setting is `Europe/London`
- **THEN** the dropdown shows `Europe/London` as the selected value

#### Scenario: Timezone defaults to UTC
- **WHEN** the settings page loads and no timezone setting exists
- **THEN** the dropdown shows `UTC` as the selected value

#### Scenario: Timezone saved on change
- **WHEN** the user selects `America/New_York` from the timezone dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"timezone": "America/New_York"}` and displays a success confirmation
