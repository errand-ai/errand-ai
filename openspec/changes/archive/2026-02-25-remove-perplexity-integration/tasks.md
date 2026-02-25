## 1. Backend — Remove Perplexity Platform

- [x] 1.1 Delete `errand/platforms/perplexity.py`
- [x] 1.2 Remove `TOOL_PROVIDER` from `PlatformCapability` enum in `errand/platforms/base.py`
- [x] 1.3 Remove `PerplexityPlatform` import and `registry.register(PerplexityPlatform())` from `errand/main.py`
- [x] 1.4 Remove the `/api/internal/credentials/{platform_id}` endpoint (`get_internal_credentials`) from `errand/main.py`
- [x] 1.5 Delete `errand/tests/test_perplexity_platform.py`

## 2. Backend — Remove Worker Perplexity Logic

- [x] 2.1 Remove the `perplexity_credentials` parameter from `process_task_in_container()` in `errand/worker.py`
- [x] 2.2 Remove the Perplexity MCP injection block (inject `perplexity-ask` into mcp_servers) from `errand/worker.py`
- [x] 2.3 Remove the Perplexity system prompt append block from `errand/worker.py`
- [x] 2.4 Remove `load_credentials("perplexity", session)` call from the task dequeue function in `errand/worker.py`
- [x] 2.5 Remove Perplexity-specific test cases from `errand/tests/test_worker.py`

## 3. Docker Compose

- [x] 3.1 Remove the `perplexity-mcp` service from `docker-compose.yml`
- [x] 3.2 Remove `PERPLEXITY_URL` env var from the worker service in `docker-compose.yml`

## 4. Container Image

- [x] 4.1 Delete the `perplexity-mcp/` directory (Dockerfile, entrypoint.sh, package.json)

## 5. Helm Chart

- [x] 5.1 Delete `helm/errand/templates/perplexity-deployment.yaml`
- [x] 5.2 Delete `helm/errand/templates/perplexity-service.yaml`
- [x] 5.3 Remove `perplexity:` section from `helm/errand/values.yaml`
- [x] 5.4 Remove `PERPLEXITY_URL` env var block from `helm/errand/templates/worker-deployment.yaml`

## 6. CI Pipeline

- [x] 6.1 Remove the `build-perplexity-mcp` job from `.github/workflows/build.yml`
- [x] 6.2 Remove `build-perplexity-mcp` from the `helm` job's `needs` array in `.github/workflows/build.yml`

## 7. Configuration

- [x] 7.1 Remove `PERPLEXITY_API_KEY` from `.env`

## 8. Specs

- [x] 8.1 Delete `openspec/specs/perplexity-platform/` directory
- [x] 8.2 Delete `openspec/specs/perplexity-mcp-deployment/` directory

## 9. Verification

- [x] 9.1 Run backend tests: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`
- [x] 9.2 Run frontend tests: `cd frontend && npm test`
- [x] 9.3 Verify `docker compose up --build` succeeds without perplexity-mcp service
- [x] 9.4 Grep codebase for remaining "perplexity" references (excluding archived changes and this change)
