## ADDED Requirements

### Requirement: plugin_poll_interval_seconds setting
The settings registry SHALL include a `plugin_poll_interval_seconds` entry with no environment variable mapping, `sensitive: false`, and a default value of `21600` (6 hours). The value SHALL be a non-negative integer in seconds. A value of `0` SHALL disable the background marketplace poller.

#### Scenario: Default value
- **WHEN** no database entry exists for `plugin_poll_interval_seconds`
- **THEN** the resolved value is `21600` with `source: "default"`

#### Scenario: Database value
- **WHEN** the database contains `plugin_poll_interval_seconds = 14400`
- **THEN** the resolved value is `14400` with `source: "database"`

#### Scenario: Zero disables poller
- **WHEN** the value is set to `0`
- **THEN** the resolved value is `0` and consumers (the background poller) interpret this as "disabled"

#### Scenario: Negative value rejected
- **WHEN** an admin attempts to set `plugin_poll_interval_seconds = -1` via `PUT /api/settings`
- **THEN** the response is HTTP 422 with a validation error
