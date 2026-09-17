## Why

The Task Management settings tab lost fields when its local components were replaced by `@errand-ai/ui-components` cards (#203, #206). The LLM timeout inputs have no visible label, so they are unidentifiable once they hold a value. `timezone` and `task_runner_log_level` are still live backend settings, but nothing in the UI can change them. Separately, the deployment-wide defaults for max turns and reasoning effort have only ever been environment variables. The task profile modal shows them as "Deployment default" but nobody can edit them. The server-level `REASONING_EFFORT` is reported by `/api/worker/defaults` yet never reaches the task runner, so the modal reports a default that is not applied.

## What Changes

- Add `max_turns` (positive integer, default `200`) and `reasoning_effort` (`low` | `medium` | `high`, default `medium`) to `SETTINGS_REGISTRY`, resolving env → DB → default via `MAX_TURNS` / `REASONING_EFFORT`.
- `PUT /api/settings` validates both new keys and `task_runner_log_level` (`DEBUG` | `INFO` | `WARNING` | `ERROR`) and `timezone` (a valid IANA zone), rejecting bad values with 422.
- The task manager forwards the resolved `max_turns` and `reasoning_effort` to every task runner when the profile does not override them. **Behaviour fix:** a server-level `REASONING_EFFORT` is now applied; previously it was silently dropped.
- `GET /api/worker/defaults` returns the resolved values (env → DB → default) instead of reading the environment directly. The response shape is unchanged.
- Stop setting `MAX_TURNS` by default in both compose files and in the Helm chart's default values. An env-sourced setting is read-only in the UI, so shipping the default as an environment variable would lock the new field in every reference deployment. The registry default (`200`) preserves today's behaviour. Operators who set `server.maxTurns` or `MAX_TURNS` explicitly keep a locked value.
- Bump `@errand-ai/ui-components` to `^0.23.0`, the release that ships the matching library change (`restore-task-settings-fields` in that repo). That release labels every `LlmModelCard` input and restores `timezone`, `task_runner_log_level`, `max_turns` and `reasoning_effort` to `TaskManagementCard`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `settings-registry`: new `max_turns` and `reasoning_effort` keys; write validation for these and for `task_runner_log_level` / `timezone`.
- `task-profile-worker-resolution`: max turns and reasoning effort inherit from the resolved global setting when the profile value is null, and the worker-defaults endpoint reports resolved values.
- `admin-settings-ui`: the Task Management tab exposes timezone, runner log level, max turns and reasoning effort, and every LLM model input carries a visible label, supplied by the pinned library version.

## Impact

- Backend: `errand/settings_registry.py`, `errand/main.py` (`update_settings`, `get_worker_defaults`), `errand/task_manager.py` (`_read_settings` select list, env var assembly), plus tests.
- Deployment: `testing/docker-compose.yml`, `deploy/docker-compose.yml`, `helm/errand/values.yaml` (`server.maxTurns` default emptied; template unchanged). Existing deployments that set `MAX_TURNS` keep their value, but the field is read-only for them.
- Frontend: `frontend/package.json` pin bump; no local component changes expected.
- Cross-repo dependency: implementation waits for the ui-components release. Errand's backend half can land first, because the current cards ignore the new keys.
