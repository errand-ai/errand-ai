## Context

The `generate_title` function in `backend/llm.py` calls the LLM with a system prompt that instructs it to classify tasks and extract timing information. The system prompt (lines 122-140) tells the LLM to return `execute_at` as "ISO 8601 UTC" and gives examples like "at 5pm" and "tomorrow", but provides no reference point for what "now" or "today" actually is. The user message (line 143) is simply `f"Classify this task:\n\n{description}"` with no timestamp.

This means when a user creates a task like "remind me in 10 minutes" or "every 30 minutes, check the server", the LLM either guesses a date (often from its training data) or returns null for `execute_at`.

The settings infrastructure already supports arbitrary key-value pairs via the `Setting` model (`settings` table, JSONB values). The frontend `SettingsPage.vue` currently has sections for System Prompt, LLM Models, and MCP Server Configuration.

## Goals / Non-Goals

**Goals:**
- Give the LLM accurate datetime context so it can resolve relative time references to concrete ISO 8601 timestamps
- Allow users to configure their timezone so "at 5pm" or "end of working day" resolves correctly
- Ensure `execute_at` is always populated for `immediate` tasks (set by backend, not LLM)
- Keep the change minimal — modify the system prompt and the call site, not the parsing or response format

**Non-Goals:**
- Changing the LLM response format (still JSON with the same fields)
- Natural language date parsing on the backend (the LLM handles this)
- Per-user timezone (this is a global admin setting — single-tenant app)
- Changing the worker's task processing system prompt (separate concern)

## Decisions

### 1. Inject current datetime into the system prompt

**Decision**: Append a line to the system prompt: `f"- The current date and time is: {now_utc} (UTC). The user's local timezone is: {timezone}."` where `now_utc` is `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` and `timezone` is the configured timezone setting.

**Rationale**: The system prompt is where the LLM gets its instructions and context. Adding the current datetime here (rather than in the user message) keeps it as a persistent reference the model can use when interpreting any time expression in the task description. Placing it in the "Rules" section alongside the other bullet points is natural.

**Alternative considered**: Inject into the user message alongside the task description — this works but mixes context with content, making the prompt less clean. The system message is the appropriate place for reference data.

### 2. Pass datetime as a parameter to `generate_title`

**Decision**: Add an optional `now: datetime | None = None` parameter to `generate_title`. If not provided, default to `datetime.now(timezone.utc)`. The caller in `main.py` passes `datetime.now(timezone.utc)` explicitly.

**Rationale**: Making `now` injectable allows tests to assert on the exact datetime included in the prompt without mocking `datetime.now`. The default keeps the function usable without change by any other caller.

**Alternative considered**: Read `datetime.now()` inside `generate_title` directly — harder to test, requires mocking `datetime`.

### 3. Timezone as a `timezone` setting in the settings table

**Decision**: Store the user's timezone as a `timezone` key in the `settings` table (e.g. value `"Europe/London"`). Default to `"UTC"` if not set. The `generate_title` function reads this setting from the same DB session it already receives.

**Rationale**: The `Setting` model already supports arbitrary key-value pairs. The settings API (`GET/PUT /api/settings`) already handles any keys — no backend endpoint changes needed. The frontend settings page needs a new timezone selector section, but the save/load infrastructure is already in place.

**Alternative considered**: Environment variable — doesn't allow runtime changes without restart; inconsistent with other settings (model, prompt) that are database-driven.

### 4. Backend sets `execute_at` for immediate tasks

**Decision**: After the LLM returns a result with `category == "immediate"`, the backend sets `execute_at = datetime.now(timezone.utc)` regardless of what the LLM returned for that field. This happens in the task creation endpoint in `main.py` (around line 280).

**Rationale**: The spec already says "For `immediate` tasks, `execute_at` SHALL be set to the current time at creation." This was previously relying on the LLM returning "approximately now", which is unreliable. The backend knows the exact current time — it should set it directly.

**Alternative considered**: Trust the LLM now that it has datetime context — unnecessary indirection when the backend knows the exact time and the spec says it should be "now".

### 5. Frontend timezone selector on Settings page

**Decision**: Add a "Timezone" section to `SettingsPage.vue` with a `<select>` dropdown of common IANA timezone names. Save via the existing `PUT /api/settings` endpoint with key `timezone`. Load from `GET /api/settings` like other settings.

**Rationale**: A `<select>` with common timezones is simpler than a free-text input (which risks typos like "Europ/London"). The `Intl.supportedValuesOf('timeZone')` browser API provides the full IANA timezone list, so no hardcoded list is needed.

**Alternative considered**: Free-text input with validation — worse UX, requires backend validation of timezone strings.

### 6. Reading the timezone setting in the LLM call path

**Decision**: In `generate_title`, query the `timezone` setting from the DB using the session that's already passed in (same pattern as `_get_model` which reads `llm_model`). Cache is unnecessary given the 5-second LLM timeout dwarfs a single DB read.

**Rationale**: Consistent with how `_get_model` already reads settings. The DB session is already available. One extra query per task creation is negligible.

## Risks / Trade-offs

- **[LLM may still misinterpret times]** → Mitigation: the datetime context significantly improves accuracy but doesn't guarantee it. The "Needs Info" tag and manual editing remain as fallbacks for edge cases.
- **[Timezone list size]** → `Intl.supportedValuesOf('timeZone')` returns ~400+ entries. → Mitigation: the `<select>` element handles this natively with search-on-type; no custom autocomplete needed.
- **[Clock skew]** → The server's UTC clock is the reference, not the user's browser clock. → Mitigation: server time is authoritative; this is a feature, not a bug — consistent regardless of which browser creates the task.
- **[Test changes]** → Existing LLM tests mock the chat completion call and assert on the response, not the prompt content. Tests that construct `generate_title` calls will need to account for the new `now` parameter. → Mitigation: the default `now=None` makes the parameter backwards-compatible.

## Open Questions

_(none)_
