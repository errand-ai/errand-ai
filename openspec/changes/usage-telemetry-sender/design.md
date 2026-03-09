## Context

errand-server is a FastAPI application with a background worker process that executes tasks via container runtimes. It has an established settings registry pattern where settings are stored in the database, configurable via the Settings UI, and overridable by environment variables (env var takes precedence, UI becomes readonly).

A companion change on errand-cloud adds a `POST /api/telemetry/report` endpoint to receive telemetry. This change implements the sender side: collecting metrics, detecting deployment type, and periodically posting reports.

Deployment types: Kubernetes (Helm chart), macOS desktop with Apple containers, macOS desktop with Docker, Docker Compose (default/other).

## Goals / Non-Goals

**Goals:**
- Generate and persist a unique installation UUID
- Collect usage metrics (tasks completed, tasks scheduled, pending count) at report time
- Detect deployment type automatically, distinguishing Apple container runtimes from Docker on macOS
- Post telemetry to errand-cloud every 6 hours
- Provide an opt-out setting via the settings registry and Settings UI
- Ensure only one server replica reports telemetry in multi-replica deployments

**Non-Goals:**
- Collecting any PII or user-identifiable information
- Tracking individual task content or prompts
- Real-time telemetry streaming
- Configuring the errand-cloud URL dynamically (hardcoded to the production endpoint)

## Decisions

### 1. Installation ID stored in settings table

**Decision**: Store the `telemetry_installation_id` as a setting in the existing `settings` table (key: `telemetry_installation_id`), auto-generated as a UUID4 on first telemetry run if not present.

**Rationale**: Reuses existing infrastructure. The settings table already has get/set patterns. No migration needed — just a new key-value pair. If the database is reset, a new UUID is generated naturally.

**Alternative considered**: Dedicated `telemetry` table — unnecessary overhead for a single value.

### 2. Telemetry target URL hardcoded

**Decision**: The errand-cloud telemetry endpoint URL is a constant (`https://service.errand.cloud/api/telemetry/report`), not a configurable setting.

**Rationale**: There's no use case for pointing telemetry at a different server. Hardcoding avoids exposing an internal implementation detail in the settings UI. The URL can be changed via a code update if needed.

### 3. Metrics collected from database at report time

**Decision**: Instead of accumulating in-memory counters, query the database at report time for usage metrics. Tasks completed since the last successful report are counted from the `tasks` table using `updated_at` timestamps, grouped by hour. Scheduled and pending counts are point-in-time snapshots. The timestamp of the last successful report is stored in the settings table (`telemetry_last_report_at`).

**Rationale**: The server process doesn't directly observe task completions (the worker does). Querying the database eliminates cross-process synchronization. The query is lightweight and runs at most once every 6 hours. No in-memory state to lose on crash.

**Alternative considered**: In-memory hourly buckets accumulated in the worker — required the reporter to run in the worker process, preventing use of the server's established Valkey locking pattern for multi-replica safety.

### 4. Telemetry reporter runs in the server process with Valkey lock

**Decision**: The periodic telemetry reporter runs as a background asyncio task in the errand-server process (alongside the scheduler and zombie cleanup). It acquires a Valkey distributed lock (`errand:telemetry-lock`) before each report cycle, following the same pattern as the scheduler.

**Rationale**: The server may be deployed with multiple replicas. Using the same Valkey lock pattern as the scheduler ensures only one replica reports per cycle. The worker process may also have multiple replicas and lacks this locking infrastructure. Since metrics come from the shared database, any server replica can collect and report them.

**Alternative considered**: Running in the worker process — workers can scale to multiple replicas and don't have the Valkey locking pattern, leading to duplicate reports.

### 5. Deployment type detection logic

**Decision**: Auto-detect at startup with this priority:
1. If `/var/run/secrets/kubernetes.io` exists → `kubernetes`
2. If `APPLE_CONTAINER_RUNTIME` environment variable is `apple` → `macos-apple`
3. If `APPLE_CONTAINER_RUNTIME` environment variable is set to any other value → `macos-docker`
4. Otherwise → `docker-other`

Cache the result at startup (deployment type doesn't change at runtime).

**Rationale**: These signals are reliable and non-overlapping. The errand-desktop app sets `APPLE_CONTAINER_RUNTIME` to indicate both that it's running on macOS and which container runtime is in use. Differentiating `macos-apple` from `macos-docker` enables tracking adoption of the Apple container runtime separately.

### 6. Fire-and-forget POST with retry

**Decision**: Use `httpx.AsyncClient` to POST telemetry. On failure (network error, non-2xx), log a warning. The next cycle will naturally pick up any completions since the last successful report (tracked via `telemetry_last_report_at`).

**Rationale**: Telemetry is best-effort. Data loss from occasional failures is acceptable. Retrying on the next cycle is simple and handles transient outages.

## Risks / Trade-offs

- **Completed task counting gap**: Tasks that transition through `completed` to `archived` between report cycles could be missed if only counting `status='completed'`. Mitigated by counting tasks with `updated_at` in the reporting window that have status `completed` OR `archived` (since archiving means they were completed).
- **No high-water mark for pending**: Unlike in-memory accumulation, querying at report time only gives a point-in-time pending count, not the peak. Acceptable for aggregate analytics.
- **Hardcoded URL**: If the telemetry endpoint URL changes, a code update is required. Mitigation: URL changes are rare and would be part of a versioned release.
