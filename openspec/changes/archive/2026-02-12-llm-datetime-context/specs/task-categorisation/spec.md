## MODIFIED Requirements

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

## ADDED Requirements

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
