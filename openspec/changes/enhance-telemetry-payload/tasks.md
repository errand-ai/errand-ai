## 1. Dependencies

- [x] 1.1 Add `psutil` to `errand/requirements.txt`

## 2. System Metrics Collection

- [x] 2.1 Implement cgroup v2/v1 container memory limit detection (returns MB or None)
- [x] 2.2 Implement cgroup v2/v1 container CPU limit detection (returns float or None)
- [x] 2.3 Implement `collect_system_metrics()` using psutil — cpu_count, memory_total_mb, memory_available_mb, container limits, disk_available_mb
- [x] 2.4 Add module-level caching for static system values (cpu_count, memory_total_mb, container limits) — only dynamic values (available memory, disk) re-read each cycle

## 3. Infrastructure Info Collection

- [x] 3.1 Implement `collect_postgres_version(session)` — execute `SELECT version()`, parse version string, return version or None
- [x] 3.2 Implement `collect_valkey_info()` — use `get_valkey()`, run `INFO server`, parse `redis_version`, return (version, connected) tuple

## 4. LLM Config Collection

- [x] 4.1 Implement `classify_provider_url(base_url, provider_type)` — pattern matching against well-known providers (openai, anthropic, gemini, xai, ollama) with litellm-other/openai-compatible-other/other fallback
- [x] 4.2 Implement `collect_llm_config(session)` — query all LlmProvider rows for provider list, query model settings (llm_model, task_processing_model, transcription_model) for model map

## 5. Health Snapshot Collection

- [x] 5.1 Record process start time at module level for uptime calculation
- [x] 5.2 Implement `collect_health_snapshot(session, since)` — uptime_seconds, task_failure_count (tasks with status='failed' since last report)

## 6. Payload Assembly and Integration

- [x] 6.1 Restructure `_send_report()` to assemble the new payload with system, infrastructure, llm, and health sections alongside existing top-level fields
- [x] 6.2 Update `collect_system_info()` signature — incorporate cached static metrics, accept worker_count param

## 7. Tests

- [x] 7.1 Unit tests for cgroup v2/v1 memory and CPU limit detection (mock file reads)
- [x] 7.2 Unit tests for `classify_provider_url` — all provider categories including edge cases
- [x] 7.3 Unit tests for `collect_system_metrics` (mock psutil)
- [x] 7.4 Unit tests for `collect_postgres_version` and `collect_valkey_info`
- [x] 7.5 Unit tests for `collect_llm_config` — providers, model settings, empty state
- [x] 7.6 Unit tests for `collect_health_snapshot` — with/without previous report time
- [x] 7.7 Integration test for full payload assembly in `_send_report` — verify structure includes all new sections
