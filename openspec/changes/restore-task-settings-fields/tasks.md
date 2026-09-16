## 1. Branch and version

- [x] 1.1 Create branch `restore-task-settings-fields` from `main` and bump `VERSION` (minor); verify with `git diff main -- VERSION`

## 2. Settings registry and validation

- [x] 2.1 Add `max_turns` (`MAX_TURNS`, default `200`) and `reasoning_effort` (`REASONING_EFFORT`, default `"medium"`) to `SETTINGS_REGISTRY`; verify with new `test_settings_registry.py` cases for default, database and env resolution, including `readonly: true` under env
- [x] 2.2 Replace the inline `plugin_poll_interval_seconds` check in `update_settings` with a key → validator table covering `max_turns`, `reasoning_effort` (reusing `VALID_REASONING_EFFORTS`), `task_runner_log_level` and `timezone` (`zoneinfo`); verify with `test_settings.py` cases for every 422 scenario in the settings-registry delta, plus the existing poll-interval tests still passing
- [x] 2.3 Make `null` for `max_turns` / `reasoning_effort` delete the stored row, while an env-sourced key still refuses the write; verify with a `test_settings.py` case for the "Null clears the stored override" scenario
- [x] 2.4 Assert that `Europe/London` validates in the test suite, so a missing tz database fails CI; add `tzdata` to `errand/requirements.txt` only if it does not validate

## 3. Runtime resolution

- [x] 3.1 In `_read_settings`, resolve `max_turns` and `reasoning_effort` with `resolve_setting_value` and store them in the settings dict; verify with a `test_task_manager.py` case asserting both keys are present with defaults on an empty database
- [x] 3.2 In the env assembly, set `MAX_TURNS` / `REASONING_EFFORT` from the profile override, otherwise from the resolved setting; verify with `test_task_manager.py` cases for every scenario in the task-profile-worker-resolution delta (profile override, DB inheritance, env inheritance, defaults)
- [x] 3.3 Make `get_worker_defaults` return the resolved values as strings; verify with endpoint tests for the default, database and env scenarios

## 4. Deployment defaults

- [x] 4.1 Remove `MAX_TURNS: "200"` from `testing/docker-compose.yml` and `deploy/docker-compose.yml`; verify with `grep -n MAX_TURNS testing/docker-compose.yml deploy/docker-compose.yml` returning nothing
- [x] 4.2 Empty the `server.maxTurns` default in `helm/errand/values.yaml`, keeping the template guard; verify with `helm template helm/errand | grep -c MAX_TURNS` returning 0, and 1 with `--set server.maxTurns=50`
- [x] 4.3 Update CLAUDE.md where it describes runner env settings, to note that `max_turns` / `reasoning_effort` are now registry settings; verify by reading the diff

## 5. Frontend library pin

- [x] 5.1 Once ui-components `0.23.0` (change `restore-task-settings-fields`) is published, bump `@errand-ai/ui-components` in `frontend/package.json` to `^0.23.0` and update the lockfile; verify with `npm ls @errand-ai/ui-components`
- [x] 5.2 Confirm that `GET /api/llm/providers/{id}/models` items carry `supports_reasoning` (true, false or null), so the library's reasoning warnings appear; verify with an existing or new endpoint test
- [x] 5.3 Update `frontend/src/pages/__tests__` Task Management tests (or add one) to assert that the four restored/new fields render and that the LLM timeout inputs have labels, using the real published components; verify with `npm test` in `frontend/`

## 6. Verification

- [x] 6.1 Run the full errand suite (`DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/`) and the frontend suite, and confirm both are green
- [x] 6.2 With `docker compose -f testing/docker-compose.yml up --build`, check on `/settings/tasks` that every timeout is labelled, and that timezone, log level, max turns and reasoning effort save and survive a reload; check that the profile modal shows the edited max turns default; run one task and confirm from its container env or logs that `MAX_TURNS` / `REASONING_EFFORT` match the saved values
- [ ] 6.3 After CI builds the PR, confirm that the ArgoCD `errand` app syncs healthy and repeat the `/settings/tasks` smoke check on the deployment
- [ ] 6.4 Run `openspec archive restore-task-settings-fields -y`, stage only the change directory and the updated `openspec/specs/` files by explicit path, commit on the branch, and re-verify the redeployed post-archive build

## Post-merge notes

- Merge the PR only after 6.3 and 6.4 pass.
- After merging, delete the local branch and confirm the `main` build deploys cleanly.
