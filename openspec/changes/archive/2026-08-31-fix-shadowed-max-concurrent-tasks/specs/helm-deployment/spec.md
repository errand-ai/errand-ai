## MODIFIED Requirements

### Requirement: max_concurrent_tasks in server env vars

The Helm chart SHALL pass `MAX_CONCURRENT_TASKS` to the server Deployment from `values.server.maxConcurrentTasks` if set. `values.yaml` SHALL NOT provide a default for `server.maxConcurrentTasks`, so a default install emits no `MAX_CONCURRENT_TASKS` env var and the setting resolves from the database (or the registry default) and remains editable via `PUT /api/settings`.

#### Scenario: Custom concurrency limit

- **WHEN** `server.maxConcurrentTasks` is set to 5
- **THEN** the server Deployment includes `MAX_CONCURRENT_TASKS=5`

#### Scenario: Default install leaves concurrency editable

- **WHEN** the chart is rendered with no `server.maxConcurrentTasks` value
- **THEN** the server Deployment SHALL NOT include a `MAX_CONCURRENT_TASKS` env var
- **AND** `GET /api/settings` SHALL report `max_concurrent_tasks` with `readonly: false`

### Requirement: Helm values defaults
The values.yaml SHALL include default probe configuration for the server. The values.yaml SHALL NOT default any key that binds to a `SETTINGS_REGISTRY` entry with an `env_var`, because such a default silently makes that setting readonly in the admin settings API on every deployment.

#### Scenario: Default health values present
- **WHEN** values.yaml is read
- **THEN** server probe configuration SHALL be present with defaults

#### Scenario: No env-bound tunable is defaulted
- **WHEN** the chart is rendered with default values
- **THEN** no env var backing a `SETTINGS_REGISTRY` key SHALL be emitted solely because of a `values.yaml` default
