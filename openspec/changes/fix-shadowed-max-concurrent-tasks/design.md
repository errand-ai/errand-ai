## Context

`SETTINGS_REGISTRY` resolves every registered setting env → DB → default
(`errand/settings_registry.py:126`). An env var that is set and non-empty wins
outright and stamps the key `source: "env"`, `readonly: true`. `PUT
/api/settings` mirrors that precedence by skipping such keys:

```python
meta = SETTINGS_REGISTRY.get(key)
if meta and meta["env_var"]:
    env_val = os.environ.get(meta["env_var"])
    if env_val is not None and env_val != "":
        continue          # errand/main.py:1331
```

This is deliberate and specified — `admin-settings-api` currently says readonly
keys "SHALL be silently ignored". The design question is not whether to keep env
precedence (we do) but how a refusal should be communicated.

Of the settings the chart can shadow, only `MAX_CONCURRENT_TASKS`,
`HINDSIGHT_*` and `OIDC_*` are emitted at all, and only `MAX_CONCURRENT_TASKS`
is emitted unconditionally from a chart default. The OIDC keys are already
handled correctly by the consumer: `UserManagementPage.vue:45` reads
`settingsMetadata[key].readonly` and disables the field.

## Goals / Non-Goals

**Goals**
- Make `max_concurrent_tasks` editable on a default deployment.
- Make a refused write observable to an operator (logs) and to a client (response).
- Keep env precedence intact: an operator who sets the env var still wins.

**Non-Goals**
- Changing the resolution order.
- Fixing the card's rendering (separate repo).
- Auditing every registry key for whether it *should* be env-bound.

## Decisions

### Decision 1: Remove the chart default rather than special-casing the key

`values.yaml:9` is the whole defect. The template at
`server-deployment.yaml:107` is already correct (`{{- if
.Values.server.maxConcurrentTasks }}`), and `SETTINGS_REGISTRY` already
defaults the key to `3` — the same number. Deleting the values entry therefore
changes no effective concurrency anywhere while returning the key to DB control.

Alternatives rejected:
- *Drop `env_var` from the registry entry.* Removes the operator escape hatch
  and breaks any deployment that sets `MAX_CONCURRENT_TASKS` directly.
- *Make DB win over env for "tunable" keys.* Introduces a second precedence
  class that every future key must be classified into, and silently inverts the
  contract the OIDC/Hindsight keys depend on.

### Decision 2: The refusal signal is the existing per-key metadata, not a new field — plus a WARNING log

`PUT /api/settings` already returns `resolve_settings(session)`, in which a
refused key reads `{"value": 3, "source": "env", "readonly": true}`. A client
knows which keys it sent, so *sent ∩ readonly* is exactly the set of refused
keys. No response-shape change is needed for a card to render an accurate
message, and no existing consumer breaks.

What is genuinely missing is server-side visibility: today nothing is emitted
when a write is dropped, so an operator debugging "my setting won't save" has
nothing in Loki to find. The change adds one WARNING per refused key naming both
the setting key and the env var that shadows it.

Alternatives rejected:
- *HTTP 422 on a readonly key.* **Decisive counter-evidence:**
  `TaskManagementCard.save()` PUTs `{archive_after_days, max_concurrent_tasks}`
  together on every save, even when only one field is dirty. A 422 would fail the
  whole request and make the editable `archive_after_days` unsavable — turning a
  cosmetic bug into a functional regression. Other cards PUT a single key each,
  so this is not a general property we can rely on.
- *Add a top-level `skipped: [...]` to the response.* The response body is a map
  of setting keys; a sibling `skipped` key is indistinguishable from a setting
  named `skipped`, and it breaks the GET/PUT response symmetry that
  `extractSettingValue` and every card rely on.
- *Return 200 but omit refused keys from the response.* Loses the current value,
  which is exactly what the card needs to re-render.

### Decision 3: Lock the chart default with a test, not a comment

The pin was introduced in #86 alongside the registry entry and survived because
nothing asserted its absence. A rendered-template assertion that a default
`helm template` emits no `MAX_CONCURRENT_TASKS` prevents silent reintroduction.

## Risks / Trade-offs

- **An operator was relying on the chart default to hold concurrency at 3.**
  Mitigated: the registry default is also `3`, so the effective value is
  unchanged until someone edits it in the UI — which is the intended capability.
- **The DB value now takes effect without a restart.** `_update_concurrency_setting()`
  re-resolves and rebuilds the semaphore every poll cycle
  (`task_manager.py:1309`), clamped to `>= 1`. A pathological value cannot
  deadlock the manager, but a large one raises concurrency immediately. Acceptable:
  that is the point of the setting.
- **The refusal is still only visible to a client that diffs.** Until the
  component library ships the readonly-aware card, the UI behaves as it does
  today. This change makes that fix possible and makes the cause findable in
  logs; it does not by itself change what the operator sees.

## Migration Plan

None required. Removing an unset-by-default values key is backwards compatible;
operators who set `server.maxConcurrentTasks` explicitly are unaffected.

## Open Questions

- Should the WARNING be rate-limited? A client that PUTs the full settings blob
  on every save would log one line per refused key per save. Current consumers
  send partial bodies, so this is not yet a problem.
