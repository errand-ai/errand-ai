## 1. Backend — LLM Datetime Context

- [x] 1.1 Add `now: datetime | None = None` parameter to `generate_title` in `llm.py`; default to `datetime.now(timezone.utc)` when `None`
- [x] 1.2 Add a `_get_timezone` helper in `llm.py` that reads the `timezone` setting from the DB session (same pattern as `_get_model`), defaulting to `"UTC"`
- [x] 1.3 Update the system prompt in `generate_title` to append a rules line with the current UTC datetime (ISO 8601) and the configured timezone
- [x] 1.4 Update the `generate_title` call site in `main.py` to pass `now=datetime.now(timezone.utc)`

## 2. Backend — Immediate Task execute_at

- [x] 2.1 In the task creation endpoint in `main.py`, set `execute_at = datetime.now(timezone.utc)` for tasks with `category == "immediate"` after the LLM result is processed, overriding whatever the LLM returned

## 3. Frontend — Timezone Selector

- [x] 3.1 Add a `timezone` ref to `SettingsPage.vue`, loaded from `GET /api/settings` (default `"UTC"`)
- [x] 3.2 Add a "Timezone" section to the settings page template with a `<select>` dropdown populated via `Intl.supportedValuesOf('timeZone')`
- [x] 3.3 Add an `onTimezoneChange` handler that saves via `PUT /api/settings` with `{"timezone": value}`, with saving/success state feedback

## 4. Backend Tests

- [x] 4.1 Add test: `generate_title` includes the injected `now` datetime in the system prompt sent to the LLM
- [x] 4.2 Add test: `generate_title` includes the configured timezone in the system prompt
- [x] 4.3 Add test: `generate_title` defaults to `UTC` when no timezone setting exists
- [x] 4.4 Add test: task creation with `category == "immediate"` sets `execute_at` to approximately now (server time)
- [x] 4.5 Update existing LLM tests to account for the new `now` parameter (pass explicit `now` where needed)
- [x] 4.6 Run full backend test suite and fix any regressions

## 5. Frontend Tests

- [x] 5.1 Add test: timezone selector is displayed on settings page
- [x] 5.2 Add test: timezone defaults to UTC when no setting exists
- [x] 5.3 Add test: selecting a timezone triggers save to API
- [x] 5.4 Run full frontend test suite and fix any regressions
