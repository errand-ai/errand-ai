## Why

The current telemetry payload captures basic identity (os, arch, version, deployment type) and usage metrics (task counts, integrations). As we approach launch, we need richer system and infrastructure data to pre-empt diagnostics when users report problems, and LLM provider/model data to understand how the product is being used. This data will feed into the existing errand-cloud admin dashboards.

## What Changes

- Add `psutil` Python dependency for cross-platform system metrics
- Extend `collect_system_info()` to capture CPU count, memory (total + container cgroup limit), and cache results at startup
- Add infrastructure collection: PostgreSQL version, Valkey version + connectivity status
- Add LLM configuration collection: provider categories (classifying base URLs against well-known providers — OpenAI, Anthropic, Gemini, xAI, Ollama — plus litellm-other/openai-compatible-other) and model names per setting
- Add health snapshot collection: uptime, available memory, available disk, task failure count since last report
- Restructure payload into `system`, `infrastructure`, `llm`, and `health` sections (existing top-level fields remain for backward compat)
- Handle cgroups v1 and v2 for container memory/CPU limits, returning null on bare metal

## Capabilities

### New Capabilities

- `telemetry-system-metrics`: System-level metrics collection (CPU, memory, container limits, disk) using psutil and cgroup detection
- `telemetry-infrastructure-info`: Infrastructure version collection (PostgreSQL version, Valkey version and connectivity)
- `telemetry-llm-config`: LLM provider categorisation and model name collection for telemetry
- `telemetry-health-snapshot`: Point-in-time health metrics (uptime, available memory, disk, failure count)

### Modified Capabilities

- `telemetry-collection`: Payload structure changes to include new `system`, `infrastructure`, `llm`, and `health` sections; `collect_system_info()` extended and cached at startup

## Impact

- **errand/telemetry.py**: Main changes — new collection functions, payload restructuring, startup caching
- **errand/requirements.txt**: Add `psutil` dependency
- **Dockerfile**: psutil is a C extension but builds cleanly on the existing base image
- **errand-cloud**: Corresponding change needed to accept and store the new payload fields (separate change in errand-cloud repo)
- **Backward compat**: All new payload sections are additive; older errand versions omitting them will continue to work with errand-cloud
