## Context

See proposal.md for motivation. The facts that shape the approach:

- `resolve_setting_value` resolves env → DB → default. An env-sourced key comes back from `GET /api/settings` with `readonly: true`, and `PUT /api/settings` refuses to persist it (`errand/main.py`, `update_settings`).
- The task manager does not use the resolver for runner settings. `_read_settings` selects an explicit list of keys from the `settings` table, and the env var assembly then applies its own precedence per key. Today `MAX_TURNS` comes from profile > server env, and `REASONING_EFFORT` comes from the profile only; the server env is dropped.
- `GET /api/worker/defaults` reads `MAX_TURNS` / `REASONING_EFFORT` from the environment directly. The ui-components `TaskProfileEditModal` renders "Deployment default: …" from it.
- `MAX_TURNS: "200"` is set in `testing/docker-compose.yml` and `deploy/docker-compose.yml`, and Helm defaults `server.maxTurns: "200"`.
- The UI lives in `@errand-ai/ui-components` (`LlmModelCard`, `TaskManagementCard`). The matching change in that repo is also named `restore-task-settings-fields` and targets `0.23.0`. It also restores the typed-model fallback and the reasoning/non-reasoning warnings, which need `supports_reasoning` on `GET /api/llm/providers/{id}/models`. Errand already returns that field. Errand only pins the version.
- The runner already defaults `REASONING_EFFORT` to `medium` and validates `MAX_TURNS`.

## Goals / Non-Goals

**Goals:**
- One resolution path for `max_turns` / `reasoning_effort`, shared by the runner env and `/api/worker/defaults`, so the modal's "Deployment default" is always the value actually applied.
- Reference deployments ship with the new fields editable.

**Non-Goals:**
- A settings-UI card for `max_context_tokens` (still unexposed; separate change).
- Changing profile override semantics or the profile API.
- Changing the task runner itself.

## Decisions

### D1: Resolve via the registry resolver, not the `_read_settings` select list
`_read_settings`, which already holds a DB session, resolves both keys with `resolve_setting_value` and stores the results in the settings dict. The env assembly uses those values when the profile gives no override, and `get_worker_defaults` calls the same resolver.
- *Alternative:* add both keys to `_read_settings` and keep ad-hoc `os.environ.get(...) or settings.get(...)` lines, like the compaction keys. Rejected because the endpoint would need to duplicate the precedence, and the CLAUDE.md "two edits" trap would apply twice. The resolver already encodes env → DB → default and type coercion.
- Because the resolver always yields a value (the default at worst), `MAX_TURNS` and `REASONING_EFFORT` are now always injected. Behaviour is unchanged for the old defaults: 200 was in every reference deployment, and `medium` is the runner's own default.

### D2: Registry defaults `200` and `medium`
`max_turns` defaults to `200`, matching every shipped deployment rather than the runner's internal fallback of 30, which only applies when the var is absent and which no deployment hit. `reasoning_effort` defaults to `medium`, matching the runner and the `task-runner-agent` spec. The coercer targets the default's type, so `max_turns` coerces to `int` and `reasoning_effort` to `str`. An env value that fails coercion falls back to the default with a warning, which is the resolver's existing behaviour.

### D3: Remove the shipped `MAX_TURNS` default rather than invert precedence
The new field would be read-only in every reference deployment because the compose files and Helm set `MAX_TURNS`. We remove the variable from both compose files and empty `server.maxTurns` in `values.yaml`. The Helm template keeps its `if` guard, so operators can still pin a value.
- *Alternative:* resolve DB before env for these two keys. Rejected because it breaks the registry's uniform env-wins contract that the settings UI's `readonly` flag relies on.
- *Alternative:* keep the defaults and accept locked fields. Rejected because it defeats the change.

### D4: Validation in `update_settings`, alongside the existing per-key check
The existing inline `plugin_poll_interval_seconds` check becomes a small key → validator table covering `max_turns`, `reasoning_effort`, `task_runner_log_level` and `timezone`. `timezone` is validated with `zoneinfo.ZoneInfo(value)`, catching `ZoneInfoNotFoundError` and `ValueError`. Validation runs after the env-readonly check. An env-sourced key is refused whatever its value, and environment values are not validated at read time, so validating first would let a client echoing back a misconfigured env value (for example `REASONING_EFFORT=High`) fail the save of every other key in the same request. `reasoning_effort` reuses `VALID_REASONING_EFFORTS` from the profile endpoints so the two cannot drift.

### D5: `/api/worker/defaults` keeps its response shape
The endpoint returns strings (`"200"`, `"medium"`), as it does today. The library modal interpolates the value, so no library change is required for it. `null` becomes unreachable in practice, but the type stays `string | null`.

### D6: No new capability key
The four fields are part of the always-advertised `task_management` capability. An older server simply omits the new keys from `GET /api/settings`. How the card treats a missing key (hide the field rather than show an empty editable one) is the library change's decision, so errand needs nothing beyond returning the keys. Confirmed with the library change: each new field renders only when its key appears in `GET /api/settings`, and the card is gated by `task_management` alone. The library pins `^0.23.0`.

### D7: `null` deletes the override for the two new keys
The shared card sends `null` when the user clears `max_turns` or `reasoning_effort`, and it adopts the PUT response as its new baseline. `update_settings` therefore deletes the `settings` row for these keys on `null`, instead of storing JSON `null`, which would then be coerced back to the default through a warning path. The response is already the full resolved map (`resolve_settings`), so the card sees `source: "env"` or `"default"` straight away. The deletion is limited to these two keys, so `null` keeps its existing meaning for keys where `null` is a meaningful stored value.

## Risks / Trade-offs

- [An existing deployment that sets `MAX_TURNS` explicitly sees a locked field] → This is intended and signalled by the card's locked note. The server logs a warning naming the variable when a write is refused.
- [Removing `MAX_TURNS` from compose changes nothing at runtime, but an operator diffing their compose file may be surprised] → The registry default is identical (200). Call it out in the PR description.
- [`zoneinfo` needs tz data in the image] → The python base images ship `/usr/share/zoneinfo`. A test asserts that `Europe/London` validates, and CI runs in the same image family. If the data is missing, add the `tzdata` pip package.
- [Always injecting `REASONING_EFFORT=medium` for non-reasoning models] → The runner already passes `medium` by default, and the spec states providers ignore it. No change in what reaches the model.
- [Cross-repo ordering] → The backend half is safe to ship before the library release, because current cards ignore unknown keys. The pin bump is the last implementation step and is blocked on the library release.

## Migration Plan

No database migration: settings rows are created on first write. To deploy, ship the server and then bump the pin. To roll back, revert. Stored `max_turns` / `reasoning_effort` rows are then ignored and `MAX_TURNS` falls back to whatever the deployment sets. Rolling back a reference deployment should restore the compose/Helm `MAX_TURNS` default together with the code, which the revert does.
