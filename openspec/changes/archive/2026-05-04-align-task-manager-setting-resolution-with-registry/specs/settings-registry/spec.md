## ADDED Requirements

### Requirement: Per-key resolver applies env → DB → default

The `settings_registry` module SHALL expose a coroutine that resolves a single registered setting key using the order **environment variable → database row → registered default**, returning a `(value, source)` tuple where `source` is one of `"env"`, `"database"`, or `"default"`.

The resolver SHALL coerce the resolved string into the type of the registered default (int, str, JSON-decoded dict/list). When the registered default is `None`, the resolver SHALL return the raw value as-is.

When coercion fails (e.g. malformed DB string), the resolver SHALL log at warning level and SHALL return `(default, "default")` rather than raising.

The resolver SHALL accept an optional pre-fetched mapping of DB rows so callers that batch-read multiple keys can avoid one DB round-trip per key.

#### Scenario: Env value takes precedence over DB row

- **WHEN** the registry has `max_concurrent_tasks` with `env_var=MAX_CONCURRENT_TASKS`, the env var is set to `7`, and the DB row's value is `4`
- **THEN** the resolver returns `(7, "env")`

#### Scenario: DB row used when no env value

- **WHEN** the env var for a registered key is unset (or empty) and the DB row exists with value `"4"`
- **THEN** the resolver returns `(4, "database")` with the integer coercion applied

#### Scenario: Default used when env and DB both absent

- **WHEN** neither the env var nor the DB row is set for a registered integer key with default `3`
- **THEN** the resolver returns `(3, "default")`

#### Scenario: Empty env string is treated as unset

- **WHEN** the env var is set to the empty string and a DB row exists
- **THEN** the resolver returns the DB-sourced value, not the empty string

#### Scenario: Coercion failure falls back to default

- **WHEN** the DB row contains a value that cannot be coerced to the default's type (e.g. `"abc"` for an int default of `3`)
- **THEN** the resolver logs at warning level and returns `(3, "default")`

#### Scenario: Pre-fetched DB rows are honoured

- **WHEN** the caller passes a `db_rows` mapping containing the key
- **THEN** the resolver uses that value instead of executing a `SELECT` against the session

### Requirement: `resolve_settings` delegates to the per-key resolver

`settings_registry.resolve_settings` SHALL build its returned dictionary by calling the per-key resolver (above) for every non-excluded key in the registry, preserving its existing behaviour: masking sensitive values for env- and DB-sourced entries, populating `source`, `sensitive`, and `readonly` (true when `source == "env"`), and excluding keys listed in `EXCLUDED_KEYS`.

The shape of the returned dictionary, including key set and field names, SHALL NOT change.

#### Scenario: API response shape is preserved

- **WHEN** a client calls `GET /api/settings` after this refactor
- **THEN** the response payload has the same keys and same field names (`value`, `source`, `sensitive`, `readonly`) as before, and env-sourced values are still masked according to the existing rules
