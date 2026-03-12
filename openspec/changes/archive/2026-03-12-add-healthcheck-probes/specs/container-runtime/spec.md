## MODIFIED Requirements

### Requirement: Worker process health reporting
The worker process SHALL start a background HTTP health server before entering its main poll loop, allowing external systems to query worker liveness.

#### Scenario: Health server starts with worker
- **WHEN** the worker process starts
- **THEN** a daemon thread SHALL begin serving HTTP on the configured health port before the first poll iteration

#### Scenario: Health server stops with worker
- **WHEN** the worker process exits
- **THEN** the health server daemon thread SHALL terminate (daemon thread, no explicit cleanup needed)
