## Context

errand-server is a FastAPI application with a background worker process that executes tasks via container runtimes. It has an established settings registry pattern where settings are stored in the database, configurable via the Settings UI, and overridable by environment variables (env var takes precedence, UI becomes readonly).

A companion change on errand-cloud adds a `POST /api/telemetry/report` endpoint to receive telemetry. This change implements the sender side: collecting metrics, detecting deployment type, and periodically posting reports.

Deployment types: Kubernetes (Helm chart), macOS desktop (errand-desktop app), Docker Compose (default/other).

## Goals / Non-Goals

**Goals:**
- Generate and persist a unique installation UUID
- Collect hourly usage metrics (tasks completed, tasks scheduled, pending queue high-water mark)
- Detect deployment type automatically
- Post telemetry to errand-cloud every 6 hours
- Provide an opt-out setting via the settings registry and Settings UI

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

### 3. Hourly buckets accumulated in-memory with database persistence

**Decision**: Maintain hourly bucket counters in-memory (module-level dict keyed by UTC hour) for fast increment. Persist pending buckets to the database on each telemetry report cycle so they survive restarts. After a successful POST, clear the sent buckets.

**Rationale**: In-memory counters are fast for high-frequency increments (every task completion). Database persistence ensures data survives crashes between report cycles. The volume is small (at most ~6-12 hourly buckets between reports).

### 4. Telemetry reporter runs in the worker process

**Decision**: The periodic telemetry reporter runs as a background asyncio task in the worker process, not in the main web process.

**Rationale**: The worker already has the task execution lifecycle instrumented. Running the reporter in the same process avoids cross-process counter synchronization. If multiple workers are running, each reports independently — the cloud-side upsert (last write wins) handles this correctly since they share the same installation_id.

### 5. Deployment type detection logic

**Decision**: Auto-detect at startup with this priority:
1. If `/var/run/secrets/kubernetes.io` exists → `kubernetes`
2. If `APPLE_CONTAINER_RUNTIME` environment variable is set → `macos-desktop`
3. Otherwise → `docker-other`

Cache the result at startup (deployment type doesn't change at runtime).

**Rationale**: These signals are reliable and non-overlapping. The errand-desktop app already sets `APPLE_CONTAINER_RUNTIME` to tell the worker whether to use Apple containers or Docker. No new env vars needed.

### 6. Fire-and-forget POST with retry

**Decision**: Use `httpx.AsyncClient` to POST telemetry. On failure (network error, non-2xx), log a warning and retain the buckets for the next cycle. No exponential backoff — simply retry on the next 6-hour cycle.

**Rationale**: Telemetry is best-effort. Data loss from occasional failures is acceptable. Retrying on the next cycle is simple and handles transient outages. The buckets remain in memory/database until successfully sent.

## Risks / Trade-offs

- **Multi-worker deployments**: If multiple worker replicas run, they share the same installation_id but accumulate independent counters. The last report to arrive at the cloud endpoint wins for each hourly bucket. Mitigation: acceptable for aggregate analytics — the values should be similar across workers since they share the same task queue.
- **In-memory counter loss on crash**: If the worker crashes between database persistence cycles, in-progress hourly bucket data is lost. Mitigation: data loss is bounded to at most one reporting cycle (6 hours). For analytics purposes, this is acceptable.
- **Hardcoded URL**: If the telemetry endpoint URL changes, a code update is required. Mitigation: URL changes are rare and would be part of a versioned release.
