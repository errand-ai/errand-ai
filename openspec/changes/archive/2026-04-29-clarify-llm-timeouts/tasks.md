## 1. Database migration

- [x] 1.1 Create a new Alembic revision under `errand/alembic/versions/` that (a) adds `task_profiles.llm_timeout` (`sa.Integer`, nullable) and (b) `UPDATE settings SET key = 'title_generation_timeout' WHERE key = 'llm_timeout'`
- [x] 1.2 Implement the `downgrade()` half: drop the column and rename the settings key back to `llm_timeout`
- [x] 1.3 Run `alembic upgrade head` against a local Postgres instance with a seeded `llm_timeout` row and confirm the rename + new column

## 2. Backend settings + helpers

- [x] 2.1 Update `errand/settings_registry.py`: remove `llm_timeout`; add `title_generation_timeout`, `task_processing_timeout`, `transcription_timeout` (each integer, default `30`, no env var, not sensitive)
- [x] 2.2 Rename `_get_llm_timeout` in `errand/llm.py` to `_get_title_generation_timeout` and have it read the new key; update `generate_title` to call the renamed helper
- [x] 2.3 Add `_get_task_processing_timeout` and `_get_transcription_timeout` helpers in `errand/llm.py` mirroring the same pattern (default `30.0`)
- [x] 2.4 Wire `_get_transcription_timeout` into the existing transcription call site (search for the transcription `chat.completions.create`/`audio.transcriptions.create` call) so it uses the new setting

## 3. Backend task profile model + API

- [x] 3.1 Add `llm_timeout = Column(Integer, nullable=True)` to `TaskProfile` in `errand/models.py`
- [x] 3.2 Update the task-profile pydantic schemas to include `llm_timeout: Optional[int]` with a `gt=0` validator
- [x] 3.3 Update the create/update route handlers to accept and persist `llm_timeout`
- [x] 3.4 Update the GET response serialisation to include `llm_timeout`

## 4. Backend task manager propagation

- [x] 4.1 In `errand/task_manager.py`, extend the profile-resolution block (near the existing `_profile_max_turns` / `reasoning_effort` handling) to compute the effective timeout: `profile.llm_timeout` → `task_processing_timeout` setting → `30`
- [x] 4.2 Set `env_vars["LLM_REQUEST_TIMEOUT"] = str(effective_timeout)` for every dispatched task (regardless of profile)
- [x] 4.3 Confirm both `DockerRuntime` and `KubernetesRuntime` pass the env var through unchanged (no runtime-specific code expected)

## 5. Task-runner

- [x] 5.1 In `task-runner/main.py`, add a helper that reads `LLM_REQUEST_TIMEOUT` and returns `float(value)` if it parses as a positive number, else `None` with a `logger.warning(...)` for invalid input
- [x] 5.2 At the `AsyncOpenAI(...)` construction site (currently `main.py:1262`), conditionally pass `timeout=<value>` when the helper returned a value
- [x] 5.3 Decide whether to also apply the same timeout to the sync compaction client (`OpenAI(...)` construction near `main.py:1090`) — if yes, use `LLM_REQUEST_TIMEOUT` only when `COMPACTION_TIMEOUT_SECONDS` is unset; if no, leave compaction alone (capture the decision in a code comment)

## 6. Frontend Settings page

- [x] 6.1 Restructure `LlmModelSettings.vue` (and any sibling components on the Task Management page) so each of the three model selectors is followed by a sibling timeout number input
- [x] 6.2 Update `SettingsPage.vue` initial-load logic: replace the single `extractValue(data, 'llm_timeout', 30)` call with three reads — `title_generation_timeout`, `task_processing_timeout`, `transcription_timeout`
- [x] 6.3 Update the save payload in `useApi.ts` (or wherever the PUT body is built) to send all three new keys; remove the legacy `llm_timeout` field
- [x] 6.4 Add input validation: `min="1"`, `step="1"`, integer type; surface a friendly error if a non-positive value is entered
- [x] 6.5 Remove the legacy generic "LLM Timeout" input and any associated tests/labels

## 7. Frontend task profile editor

- [x] 7.1 Add an "LLM Timeout (seconds)" number input to the profile editor form, sibling to "Max Turns" and "Reasoning Effort"
- [x] 7.2 Implement blank-to-`null` semantics on save and `null`-to-blank on load
- [x] 7.3 Add the timeout summary to the profile card per the new spec scenario (`"Timeout: 180s"` or `"Timeout: (default)"`)

## 8. Tests

- [x] 8.1 Update `errand/tests/test_llm.py`: rename existing timeout tests to use `title_generation_timeout` key; verify `DEFAULT_LLM_TIMEOUT` (or its renamed equivalent) still applies when key absent
- [x] 8.2 Add `errand/tests/test_settings_registry.py` (or extend existing) coverage for the three new keys defaulting to `30`
- [x] 8.3 Add a task-profile API test for valid `llm_timeout`, `null` `llm_timeout`, and the validation errors (zero, negative)
- [x] 8.4 Add a `test_task_manager` test asserting `LLM_REQUEST_TIMEOUT` is set in `env_vars` for both no-profile and profile-with-override cases
- [x] 8.5 Add a `task-runner/test_main.py` test asserting `AsyncOpenAI` receives `timeout=120.0` when `LLM_REQUEST_TIMEOUT=120`, no `timeout` kwarg when unset, and a warning logged on invalid input
- [x] 8.6 Update existing settings-page Vitest tests (`SettingsPage.test.ts`) to expect three timeout inputs and the renamed keys in the save payload
- [x] 8.7 Add task-profile-editor frontend tests covering blank-to-null, value-to-int, and the summary formatting

## 9. Migration verification

- [x] 9.1 Verify with a local Postgres + seeded `llm_timeout = 60` that after `alembic upgrade head`, the Settings UI loads `60` into the title-generation timeout field and the other two default to `30`
- [ ] 9.2 Verify `alembic downgrade -1` restores the `llm_timeout` key and drops the column

(9.x deferred to PR-time docker-compose validation)

## 10. Docs + release

- [x] 10.1 Update `CLAUDE.md`: under "Task Processing (TaskManager)" mention `LLM_REQUEST_TIMEOUT` env var; under a new "LLM Timeouts" subsection summarise the three settings + per-profile override
- [x] 10.2 Bump `VERSION` (MINOR — additive feature; the settings-key rename is internal-only and covered by migration)
- [x] 10.3 `docker compose -f testing/docker-compose.yml up --build` end-to-end: create a task with no profile, then a task with a profile that overrides `llm_timeout`; tail the runner logs to confirm the env var lands in the container
- [x] 10.4 Open a PR; once green, verify ArgoCD-deployed images pick up the setting correctly before merge
