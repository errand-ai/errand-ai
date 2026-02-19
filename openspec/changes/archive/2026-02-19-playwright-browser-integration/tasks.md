## 1. Playwright MCP Image

- [x] 1.1 Create `playwright-mcp/Dockerfile` using `mcr.microsoft.com/playwright:v1.50.0-noble` base, install `@playwright/mcp` globally, expose port 8931, default CMD `npx @playwright/mcp --port 8931 --host 0.0.0.0`
- [x] 1.2 Create `playwright-mcp/requirements.txt` or `package.json` if needed for pinning `@playwright/mcp` version
- [x] 1.3 Build and test the image locally: verify `docker build`, container starts, and `/mcp` endpoint responds

## 2. Worker: Playwright Container Lifecycle

- [x] 2.1 Add Playwright environment variable reads to worker: `PLAYWRIGHT_MCP_IMAGE`, `PLAYWRIGHT_MEMORY_LIMIT` (default `512m`), `PLAYWRIGHT_PORT` (default `8931`), `PLAYWRIGHT_STARTUP_TIMEOUT` (default `30`)
- [x] 2.2 Implement `start_playwright_container()` function: create container with `network_mode="host"`, `--memory` and `--memory-swap` limits, start it, return container object
- [x] 2.3 Implement `health_check_playwright()` function: poll `http://localhost:{port}/mcp` with timeout, return success/failure
- [x] 2.4 Implement `cleanup_playwright_container()` function: stop and remove container, handle already-removed case (OOM-kill) gracefully
- [x] 2.5 Integrate into `process_task_in_container()`: start Playwright before task-runner, health-check, inject MCP URL into config if healthy, cleanup in `finally` block
- [x] 2.6 Implement degraded mode: if health check fails, log error, skip Playwright MCP injection, proceed without browser tools

## 3. Worker: MCP Configuration Injection

- [x] 3.1 Add Playwright MCP entry injection to the MCP config assembly logic: inject `{"playwright": {"url": "http://localhost:{port}/mcp"}}` into `mcpServers`, respecting database-configured entries (no overwrite)

## 4. Task Runner: Context Management

- [x] 4.1 Implement `strip_old_screenshots()` filter function: scan input items for `data:image/` content, retain last N (from `MAX_RETAINED_SCREENSHOTS` env var, default 5), replace older images with `[screenshot removed]`
- [x] 4.2 Create `RunConfig` with `call_model_input_filter=strip_old_screenshots` and pass to `Runner.run_streamed()`
- [x] 4.3 Add `MAX_RETAINED_SCREENSHOTS` environment variable read with default value

## 5. Helm Chart

- [x] 5.1 Add `playwrightMcp` section to `values.yaml`: `image.repository`, `image.tag`, `image.pullPolicy`, `memoryLimit`, `port`, `startupTimeout`
- [x] 5.2 Add Playwright environment variables to worker deployment template: `PLAYWRIGHT_MCP_IMAGE`, `PLAYWRIGHT_MEMORY_LIMIT`, `PLAYWRIGHT_PORT`, `PLAYWRIGHT_STARTUP_TIMEOUT`

## 6. CI Pipeline

- [x] 6.1 Add `build-playwright-mcp` job to `.github/workflows/build.yml`: build from `playwright-mcp/Dockerfile`, push to `ghcr.io/devops-consultants/content-manager-playwright-mcp`, multi-arch (`linux/amd64`, `linux/arm64`), depends on `version` and `test` jobs
- [x] 6.2 Add `build-playwright-mcp` to the `helm` job's `needs` list

## 7. Tests

- [x] 7.1 Add worker tests for Playwright container lifecycle: start, health-check success, health-check timeout (degraded mode), cleanup after task, cleanup on error
- [x] 7.2 Add worker tests for MCP config injection: Playwright entry injected, database entry not overwritten
- [x] 7.3 Add task-runner tests for screenshot filter: old screenshots stripped, recent screenshots retained, non-image items unaffected, custom retention limit
