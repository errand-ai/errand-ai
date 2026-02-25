## Why

The Perplexity integration (sidecar MCP server, platform credentials, worker injection) will be replaced by a different approach in a forthcoming change. Removing it now reduces deployment complexity (one fewer container/service) and eliminates dead code before that replacement lands.

## What Changes

- **BREAKING**: Remove the `perplexity-mcp` container, Helm deployment, and service
- **BREAKING**: Remove the `perplexity-ask` MCP tool injection from the task worker
- **BREAKING**: Remove the `/api/internal/credentials/perplexity` endpoint
- Remove the `PerplexityPlatform` class and `TOOL_PROVIDER` platform capability
- Remove the `perplexity-mcp` service from docker-compose
- Remove the `build-perplexity-mcp` CI job and Helm dependency on it
- Remove `PERPLEXITY_URL` environment variable from worker configuration
- Remove the `perplexity-mcp/` directory (Dockerfile, entrypoint, package.json)
- Delete `perplexity-platform` and `perplexity-mcp-deployment` specs
- Remove perplexity references from `task-worker`, `ci-pipelines`, and `helm-deployment` specs

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-worker`: Remove perplexity credential loading and MCP server injection
- `ci-pipelines`: Remove `build-perplexity-mcp` job and Helm dependency on it
- `helm-deployment`: Remove perplexity deployment, service, and worker env var

### Removed Capabilities

- `perplexity-platform`: Entire spec removed
- `perplexity-mcp-deployment`: Entire spec removed

## Impact

- **Backend**: `main.py` (import, registration, internal credentials endpoint), `worker.py` (credential loading, MCP injection, system prompt), `platforms/perplexity.py` (deleted), `platforms/base.py` (TOOL_PROVIDER enum value)
- **Tests**: `test_perplexity_platform.py` (deleted), `test_worker.py` (perplexity-specific cases)
- **Container**: `perplexity-mcp/` directory (deleted)
- **Docker Compose**: perplexity-mcp service and PERPLEXITY_URL env var removed
- **Helm**: `perplexity-deployment.yaml`, `perplexity-service.yaml` (deleted), `values.yaml` (perplexity section), `worker-deployment.yaml` (PERPLEXITY_URL)
- **CI**: `build-perplexity-mcp` job removed from `.github/workflows/build.yml`
- **Specs**: 2 specs deleted, 3 specs modified
- **Config**: `PERPLEXITY_API_KEY` in `.env` removed
