## MODIFIED Requirements

### Requirement: Interval parsing for simple durations

The worker SHALL parse `repeat_interval` values by first normalising human-readable formats to compact form, then matching the format `<number><unit>` where unit is `m` (minutes), `h` (hours), `d` (days), or `w` (weeks). Normalisation SHALL handle: (1) word units with optional plural (`minutes`, `minute`, `hours`, `hour`, `days`, `day`, `weeks`, `week`) mapped to their compact equivalents, (2) spaces between number and unit (`7 days` → `7d`), and (3) named intervals (`daily` → `1d`, `weekly` → `1w`, `hourly` → `1h`). If the `repeat_interval` does not match after normalisation, the worker SHALL log a warning and skip rescheduling.

#### Scenario: Parse compact minutes interval

- **WHEN** `repeat_interval` is `"30m"`
- **THEN** the parsed duration is 30 minutes

#### Scenario: Parse compact days interval

- **WHEN** `repeat_interval` is `"7d"`
- **THEN** the parsed duration is 7 days

#### Scenario: Parse human-readable days with space

- **WHEN** `repeat_interval` is `"7 days"`
- **THEN** the parsed duration is 7 days

#### Scenario: Parse human-readable singular unit

- **WHEN** `repeat_interval` is `"1 hour"`
- **THEN** the parsed duration is 1 hour

#### Scenario: Parse named interval daily

- **WHEN** `repeat_interval` is `"daily"`
- **THEN** the parsed duration is 1 day

#### Scenario: Parse named interval weekly

- **WHEN** `repeat_interval` is `"weekly"`
- **THEN** the parsed duration is 7 days

#### Scenario: Parse named interval hourly

- **WHEN** `repeat_interval` is `"hourly"`
- **THEN** the parsed duration is 1 hour

#### Scenario: Unparseable interval skips rescheduling

- **WHEN** `repeat_interval` is `"every other tuesday"` or `"0 9 * * MON-FRI"`
- **THEN** the worker logs a warning and does NOT create a new task
