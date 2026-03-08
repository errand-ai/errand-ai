## 1. Settings Registry & Telemetry Setting

- [ ] 1.1 Add `telemetry_enabled` to the settings registry with env var `TELEMETRY_ENABLED`, `sensitive: false`, default `true`
- [ ] 1.2 Add telemetry toggle to the Settings UI page: "Usage Telemetry" toggle with description, readonly when env var is set

## 2. Deployment Type Detection

- [ ] 2.1 Create `errand/telemetry.py` module with `detect_deployment_type()` function: checks `/var/run/secrets/kubernetes.io`, then `APPLE_CONTAINER_RUNTIME` env var, defaults to `docker-other`
- [ ] 2.2 Add `collect_system_info()` function: returns OS, arch, version (from `VERSION` file), and worker count

## 3. Hourly Bucket Accumulator

- [ ] 3.1 Implement `TelemetryBuckets` class in `errand/telemetry.py`: in-memory dict keyed by UTC hour string, with `increment_completed()`, `update_max_pending(current_size)`, and `get_and_clear()` methods
- [ ] 3.2 Add database persistence for unsent buckets: store as JSON in the settings table (key: `telemetry_pending_buckets`), load on startup, save on shutdown and before each report attempt
- [ ] 3.3 Add `set_tasks_scheduled(count)` method that sets the scheduled count on all pending buckets at report time

## 4. Worker Instrumentation

- [ ] 4.1 Integrate telemetry counter increments into the worker task execution loop: call `increment_completed()` after task cleanup (step 14), call `update_max_pending()` on task dequeue and after task cleanup
- [ ] 4.2 Expose the current pending queue size for telemetry (the number of tasks with status `pending` in the database or queue)

## 5. Periodic Telemetry Reporter

- [ ] 5.1 Implement `TelemetryReporter` class with async background task that runs every 6 hours: checks `telemetry_enabled` setting, collects system info + active integrations + hourly buckets, POSTs to `https://cloud.errand.ai/api/telemetry/report` via `httpx.AsyncClient`
- [ ] 5.2 Handle installation ID: generate UUID4 on first run, persist as `telemetry_installation_id` in settings, reuse on subsequent runs
- [ ] 5.3 Collect active integrations list at report time (query configured/enabled integrations)
- [ ] 5.4 Start the reporter background task in the worker process startup, register shutdown handler to persist pending buckets

## 6. Tests

- [ ] 6.1 Test deployment type detection: mock filesystem and env vars for each deployment type
- [ ] 6.2 Test hourly bucket accumulator: increment, rollover, get_and_clear, persistence round-trip
- [ ] 6.3 Test telemetry reporter: successful POST (mock httpx), failed POST (buckets retained), telemetry disabled (no POST sent)
- [ ] 6.4 Test installation ID generation and reuse
- [ ] 6.5 Test settings registry includes `telemetry_enabled` with correct defaults
