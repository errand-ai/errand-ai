## Context

The telemetry reporter (`errand/telemetry.py`) currently collects basic system info (os, arch, version, worker_count) and usage metrics (hourly task counts, integrations) and POSTs them to errand-cloud every 6 hours. The payload is flat — all fields at the top level.

As errand approaches launch, we want richer data for two purposes: (1) product insight — understanding LLM provider/model choices and infrastructure configurations, and (2) diagnostics — pre-collecting system resource data that would otherwise require back-and-forth with users reporting problems.

The errand-cloud receiver (`app/api/telemetry.py`) validates against a `TelemetryReport` Pydantic model and stores data in `TelemetryInstallation` + `TelemetryHourly` tables. Both sides need updating.

## Goals / Non-Goals

**Goals:**
- Collect system resource metrics (CPU, memory, container limits, disk) for diagnostics
- Collect infrastructure versions (PostgreSQL, Valkey) since users deploy their own
- Collect LLM provider categories and model names for product insight
- Collect health snapshots (uptime, available memory, failure count) per report cycle
- Restructure payload into logical sections while maintaining backward compatibility
- Cache static system info (CPU, total memory, container limits) at startup — don't re-read every cycle

**Non-Goals:**
- Database performance metrics (latency, slow queries) — better tools exist for this
- Python version tracking — we control the container image
- Local diagnostics endpoint (`/api/diagnostics`) — future change
- Frontend changes — no UI for the new data; it's consumed by errand-cloud admin dashboards

## Decisions

### 1. Use `psutil` for cross-platform system metrics

**Choice**: Add `psutil` as a dependency for CPU count, memory, and disk metrics.

**Alternatives considered**:
- Read `/proc` and `/sys` directly — Linux-only, fragile across distros, doesn't work on macOS local dev
- `platform` + `os` stdlib — lacks memory and disk info

**Rationale**: psutil is the de facto standard for system metrics in Python. It's well-maintained, cross-platform, and handles the platform differences we'd otherwise code ourselves. The C extension compiles cleanly on the Alpine/Debian base images we use.

### 2. Read cgroup files directly for container limits (not psutil)

**Choice**: Read cgroup v2 paths first (`/sys/fs/cgroup/memory.max`, `/sys/fs/cgroup/cpu.max`), fall back to v1 (`/sys/fs/cgroup/memory/memory.limit_in_bytes`, `/sys/fs/cgroup/cpu/cpu.cfs_quota_us` + `cpu.cfs_period_us`), return `None` if neither exists.

**Rationale**: psutil reports host-level resources, not container limits. Container limits are set by the orchestrator and exposed via cgroup filesystem. Modern K8s (containerd) uses cgroup v2; older Docker may use v1. Trying v2 first covers the common case.

### 3. Classify LLM provider base URLs into categories

**Choice**: Map base URLs to well-known provider categories using domain pattern matching:

| Pattern | Category |
|---------|----------|
| `*api.openai.com*` | `openai` |
| `*api.anthropic.com*` | `anthropic` |
| `*generativelanguage.googleapis.com*` | `gemini` |
| `*api.x.ai*` | `xai` |
| `localhost:11434` or `127.0.0.1:11434` | `ollama` |
| Any other (provider_type=litellm) | `litellm-other` |
| Any other (provider_type=openai_compatible) | `openai-compatible-other` |
| Any other | `other` |

**Rationale**: Raw base URLs could contain internal hostnames or IPs — privacy concern. Category + provider_type gives us the product insight we need (which providers are popular) without leaking infrastructure details. Model names are safe to send as-is (standard identifiers like `gpt-4o`, `claude-sonnet-4-20250514`).

### 4. Restructure payload with nested sections

**Choice**: Group new fields into `system`, `infrastructure`, `llm`, and `health` sections. Keep existing top-level fields (`os`, `arch`, `version`, `worker_count`, `integrations`, `hourly_buckets`) for backward compatibility — errand-cloud will read from both locations during transition.

```
{
  // Existing top-level (kept for compat)
  "installation_id", "deployment_type", "version", "os", "arch",
  "worker_count", "integrations", "hourly_buckets",

  // New sections
  "system": { cpu_count, memory_total_mb, memory_available_mb,
              container_memory_limit_mb, container_cpu_limit,
              disk_available_mb },
  "infrastructure": { postgres_version, valkey_version, valkey_connected },
  "llm": { providers: [{type, category}],
            models: {setting_key: {category, model}} },
  "health": { uptime_seconds, task_failure_count }
}
```

**Note**: `memory_available_mb` and `disk_available_mb` move into `system` rather than a separate `health` section — they're system metrics even if they're point-in-time. `uptime_seconds` and `task_failure_count` go in `health` as they're runtime-specific.

### 5. Cache static system info at module level

**Choice**: Collect CPU count, total memory, and container limits once (at first call or reporter init) and store in a module-level dict. Re-read dynamic values (available memory, disk) each cycle.

**Rationale**: These values never change within a process lifetime. Avoids redundant cgroup file reads and psutil calls every 6 hours.

### 6. Query PostgreSQL and Valkey versions via existing connections

**Choice**:
- PostgreSQL: `SELECT version()` via the existing async session
- Valkey: `INFO server` command via the existing `get_valkey()` connection, parse `redis_version` field

**Rationale**: No new connections needed. Both queries are lightweight. If Valkey is unavailable, report `valkey_connected: false` and `valkey_version: null`.

## Risks / Trade-offs

- **psutil C extension build**: Could fail on exotic base images → Mitigated by using standard Python base images; psutil is widely used and well-tested on Alpine/Debian
- **Cgroup path differences**: Some container runtimes may use non-standard paths → Mitigated by trying v2 then v1 with graceful fallback to null
- **Payload size increase**: More data per report → Minimal impact; still well under 1KB JSON. Sent only every 6 hours
- **errand-cloud schema migration**: New columns/tables needed → Additive migration, no data loss. Old payload format still accepted
- **Valkey INFO command permissions**: Some managed Redis/Valkey services restrict INFO → Catch exceptions, return null version with connected=true (connection works, but INFO is restricted)
