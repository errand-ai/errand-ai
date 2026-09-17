## ADDED Requirements

### Requirement: Deployment default agent limits

The settings registry SHALL define two keys that set the deployment-wide defaults a task runner uses when the task's profile does not override them:

| Key | Type | Env var | Default |
|---|---|---|---|
| `max_turns` | positive integer | `MAX_TURNS` | `200` |
| `reasoning_effort` | one of `low`, `medium`, `high` | `REASONING_EFFORT` | `medium` |

Both SHALL resolve through the standard env → DB → default order, so a deployment that sets either environment variable keeps its value and sees the setting as read-only. Neither SHALL be marked sensitive.

`PUT /api/settings` SHALL reject with HTTP 422 a `max_turns` that is not an integer ≥ 1 (booleans are not integers), and a `reasoning_effort` that is not one of the three allowed values. `reasoning_effort` SHALL be compared case-sensitively against the lower-case values.

For these two keys, a `null` value in `PUT /api/settings` SHALL delete the stored override, so the key resolves to its environment value or its default. A `null` for an env-sourced key is refused like any other write to it. As for every key, the response is HTTP 200 with the full resolved settings map.

#### Scenario: Unset keys resolve to defaults
- **WHEN** neither key is stored and neither `MAX_TURNS` nor `REASONING_EFFORT` is set
- **THEN** `GET /api/settings` reports `max_turns` as `200` and `reasoning_effort` as `medium`, each with `source: "default"`

#### Scenario: Stored value is editable
- **WHEN** an admin sends `PUT /api/settings` with `{"max_turns": 50, "reasoning_effort": "high"}` and neither environment variable is set
- **THEN** both values are stored and `GET /api/settings` reports them with `source: "database"` and `readonly: false`

#### Scenario: Environment locks the value
- **WHEN** `MAX_TURNS=300` is set and an admin sends `PUT /api/settings` with `{"max_turns": 50}`
- **THEN** the stored value is not changed and `GET /api/settings` reports `max_turns` as `300` with `source: "env"` and `readonly: true`

#### Scenario: Null clears the stored override
- **WHEN** `max_turns` is stored as `50`, `MAX_TURNS` is not set, and an admin sends `PUT /api/settings` with `{"max_turns": null}`
- **THEN** the stored row is removed and the response reports `max_turns` as `200` with `source: "default"`

#### Scenario: Invalid max turns rejected
- **WHEN** an admin sends `PUT /api/settings` with `{"max_turns": 0}`, `{"max_turns": "ten"}` or `{"max_turns": true}`
- **THEN** the response is HTTP 422 and nothing is stored

#### Scenario: Invalid reasoning effort rejected
- **WHEN** an admin sends `PUT /api/settings` with `{"reasoning_effort": "extreme"}`
- **THEN** the response is HTTP 422 and nothing is stored

### Requirement: Task runner log level and timezone validation

`PUT /api/settings` SHALL reject with HTTP 422 a `task_runner_log_level` that is not one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, and a `timezone` that is not a valid IANA time zone name. Both keys keep their existing registry entries (no environment variable, defaults `INFO` and `UTC`).

#### Scenario: Valid values stored
- **WHEN** an admin sends `PUT /api/settings` with `{"task_runner_log_level": "DEBUG", "timezone": "Europe/London"}`
- **THEN** both values are stored and returned by `GET /api/settings`

#### Scenario: Unknown log level rejected
- **WHEN** an admin sends `PUT /api/settings` with `{"task_runner_log_level": "TRACE"}`
- **THEN** the response is HTTP 422 and nothing is stored

#### Scenario: Unknown timezone rejected
- **WHEN** an admin sends `PUT /api/settings` with `{"timezone": "Mars/Olympus"}`
- **THEN** the response is HTTP 422 and nothing is stored
