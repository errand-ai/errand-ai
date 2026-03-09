## 1. Settings Registry & Telemetry Setting

- [x] 1.1 Add `telemetry_enabled` to the settings registry with env var `TELEMETRY_ENABLED`, `sensitive: false`, default `true`
- [x] 1.2 Add telemetry toggle to the Settings UI page: "Usage Telemetry" toggle with description, readonly when env var is set

## 2. Deployment Type Detection

- [x] 2.1 Create `errand/telemetry.py` module with `detect_deployment_type()` function: checks `/var/run/secrets/kubernetes.io`, then `ERRAND_CONTAINER_RUNTIME` env var (passthrough value), defaults to `unknown-docker`
- [x] 2.2 Use `ERRAND_CONTAINER_RUNTIME` value directly as deployment type — supports `apple-container`, `apple-docker`, `windows-docker`, `linux-docker`, etc.
- [x] 2.3 Add `collect_system_info()` function: returns OS, arch, version (from `VERSION` file), and worker count

## 3. Move Reporter from Worker to Server

- [x] 3.1 Remove TelemetryBuckets, TelemetryReporter, and all telemetry instrumentation from `worker.py` (increment_completed, update_max_pending, reporter start/stop)
- [x] 3.2 Replace in-memory hourly bucket accumulation with DB queries at report time: count tasks completed since last report grouped by hour, snapshot pending/scheduled counts
- [x] 3.3 Store `telemetry_last_report_at` in settings table to track the window for completed task counting
- [x] 3.4 Add Valkey distributed lock (`errand:telemetry-lock`) to TelemetryReporter following the same pattern as scheduler/zombie cleanup
- [x] 3.5 Start TelemetryReporter as a background asyncio task in `main.py` lifespan (alongside scheduler, zombie cleanup), register cancel on shutdown
- [x] 3.6 Remove TelemetryBuckets class and DB persistence helpers (save_buckets_to_db, load_buckets_from_db, clear_buckets_in_db) — no longer needed

## 4. Installation ID & Integrations

- [x] 4.1 Handle installation ID: generate UUID4 on first run, persist as `telemetry_installation_id` in settings, reuse on subsequent runs
- [x] 4.2 Collect active integrations list at report time (query configured/enabled integrations)

## 5. Tests

- [x] 5.1 Test deployment type detection: mock filesystem and env vars for each deployment type
- [x] 5.2 Update deployment type tests for macos-apple vs macos-docker distinction
- [x] 5.3 Update telemetry reporter tests: remove bucket-based tests, add DB-query-based report tests, test Valkey lock acquisition, test server-side lifecycle
- [x] 5.4 Test installation ID generation and reuse
- [x] 5.5 Test settings registry includes `telemetry_enabled` with correct defaults
