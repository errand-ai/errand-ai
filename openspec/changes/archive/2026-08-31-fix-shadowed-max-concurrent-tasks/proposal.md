## Why

`Max concurrent tasks` cannot be changed from the settings UI on any deployed
instance. Saving appears to succeed and the field silently reverts to `3`.

The cause is a chart default, not a UI bug. `helm/errand/values.yaml` sets
`server.maxConcurrentTasks: 3`, so the server Deployment always carries
`MAX_CONCURRENT_TASKS=3`. `resolve_setting_value` resolves env → DB → default,
so the env value wins and `PUT /api/settings` skips the key entirely
(`update_settings` in `errand/main.py`), returning HTTP 200 with the unchanged value. Nobody
chose to pin this tunable — it is boilerplate that makes an operator-facing
setting permanently readonly on every deployment (no values file overrides it:
rancher, cloud, and sh all inherit the chart default).

The second half of the problem is that the refusal is invisible. The current
spec says readonly keys "SHALL be silently ignored", so a rejected write is
indistinguishable from an accepted one — to the operator, to the calling card,
and in the server logs. Every env-bound key in `SETTINGS_REGISTRY` carries the
same trap; `max_concurrent_tasks` is simply the first one a chart default armed.

## What Changes

- Remove `server.maxConcurrentTasks` from `helm/errand/values.yaml` so the
  env var is emitted only when an operator deliberately sets it. The template is
  already `{{- if }}`-guarded and the registry default is also `3`, so behaviour
  is unchanged for anyone who never touched it, and the value remains available
  as an escape hatch for operators who do want to pin it.
- `PUT /api/settings` SHALL no longer refuse a key *silently*: each refused key
  is logged at WARNING naming the key and the shadowing env var, and the
  response's existing per-key `readonly`/`source` metadata is the machine-readable
  signal a client diffs its request against.
- Add regression coverage locking both halves: the chart emits no
  `MAX_CONCURRENT_TASKS` by default, and a PUT to an env-shadowed key neither
  persists nor reports success for that key.

Not in scope: the settings card renders an editable input and an enabled Save
button for a key the API already reports as `readonly: true`. That fix lives in
`errand-ai/errand-component-library` (change `surface-readonly-settings`) and
consumes the contract this change locks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `helm-deployment`: `MAX_CONCURRENT_TASKS` is emitted only on explicit opt-in;
  `values.yaml` SHALL NOT default a tunable that the settings API can otherwise manage.
- `admin-settings-api`: readonly keys are refused observably rather than silently.

## Impact

- `helm/errand/values.yaml` — remove one default (chart minor bump).
- `errand/main.py` `update_settings` — add the WARNING log on refusal.
- `errand/tests/` — new coverage; `helm/errand/tests/` or template-render check
  for the values default.
- Behavioural: on the next deploy, `max_concurrent_tasks` becomes DB-editable and
  `_update_concurrency_setting()` picks it up on the next poll cycle without a
  restart. Deployments that relied on the chart default keep the same effective
  value (registry default `3`).
- Downstream: `errand-component-library` depends on the response contract this
  change states explicitly.
