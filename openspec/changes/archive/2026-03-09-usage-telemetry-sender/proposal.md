## Why

There is no visibility into how many errand-server installations are running, what integrations are popular, or how the platform is being used. The errand-cloud service is adding a telemetry receiver endpoint — this change implements the client side: collecting usage data and periodically posting it to errand-cloud.

## What Changes

- New `telemetry_installation_id` generated on first run and persisted in the database
- New `telemetry_enabled` setting (default `true`) following the existing settings registry pattern: configurable via Settings UI, overridable by `TELEMETRY_ENABLED` environment variable
- Hourly bucket accumulator tracking `tasks_completed`, `tasks_scheduled`, and `max_pending` (pending queue high-water mark) per UTC hour
- Periodic telemetry reporter (every 6 hours) that POSTs accumulated data to `POST /api/telemetry/report` on errand-cloud
- Deployment type auto-detection: Kubernetes (via `/var/run/secrets/kubernetes.io`), macOS desktop (via errand-desktop environment variables), default `docker-other`
- System information collection: OS, architecture, errand version, worker count, active integrations list

## Capabilities

### New Capabilities
- `telemetry-collection`: Hourly bucket accumulation, system info gathering, deployment type detection, and periodic reporting to errand-cloud
- `telemetry-settings`: Opt-out telemetry setting integrated with the settings registry and Settings UI

### Modified Capabilities
- `settings-registry`: Adding `telemetry_enabled` to the settings registry with env var `TELEMETRY_ENABLED` mapping
- `task-worker`: Adding instrumentation to track task completion counts and pending queue high-water mark for telemetry buckets

## Impact

- New database row for `telemetry_installation_id` in settings (or dedicated table)
- New background task in the worker or main process for periodic telemetry posting
- New HTTP dependency: outbound POST to errand-cloud telemetry endpoint (fire-and-forget, no auth required)
- Settings UI: new toggle for telemetry opt-out
- Worker: counter increments on task state transitions
