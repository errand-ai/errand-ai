## 1. Platform Abstraction

- [x] 1.1 Add `TOOL_PROVIDER = "tool_provider"` to `PlatformCapability` enum in `backend/platforms/base.py`
- [x] 1.2 Create `backend/platforms/perplexity.py` with `PerplexityPlatform` class: `info()` returning id/label/capabilities/credential_schema, and `verify_credentials()` making a test API call to Perplexity
- [x] 1.3 Register `PerplexityPlatform` in the platform registry during app startup (in `backend/main.py` lifespan)
- [x] 1.4 Add backend tests for `PerplexityPlatform.info()` and credential verification

## 2. Internal Credentials Endpoint

- [x] 2.1 Add `GET /api/internal/credentials/{platform_id}` endpoint in `backend/main.py` — no auth, returns decrypted credentials (200) or 404
- [x] 2.2 Add backend tests for the internal credentials endpoint (credentials exist, not found, unknown platform)

## 3. Perplexity MCP Docker Image

- [x] 3.1 Create `perplexity-mcp/package.json` with `@perplexity-ai/mcp-server` dependency and `start:http:public` script
- [x] 3.2 Create `perplexity-mcp/entrypoint.sh` — polls backend for credentials, sets `PERPLEXITY_API_KEY`, execs `npm run start:http:public`
- [x] 3.3 Create `perplexity-mcp/Dockerfile` — `node:22-slim` base, npm install, copy entrypoint, set entrypoint

## 4. Worker Changes

- [x] 4.1 Update `backend/worker.py` to replace `USE_PERPLEXITY` env var check with `load_credentials("perplexity", session)` call for Perplexity MCP injection
- [x] 4.2 Add/update worker tests for Perplexity injection based on platform credentials

## 5. Helm Chart Updates

- [x] 5.1 Update `helm/content-manager/templates/perplexity-deployment.yaml` — remove `existingSecret` conditional, add `BACKEND_URL` env var, remove `envFrom` secret reference, gate on `.Values.perplexity.enabled`
- [x] 5.2 Update `helm/content-manager/templates/perplexity-service.yaml` — gate on `.Values.perplexity.enabled` instead of `existingSecret`
- [x] 5.3 Update `helm/content-manager/templates/worker-deployment.yaml` — remove `USE_PERPLEXITY` env var, keep `PERPLEXITY_URL` gated on `.Values.perplexity.enabled`
- [x] 5.4 Update `helm/content-manager/values.yaml` — remove `perplexity.existingSecret`, add `perplexity.enabled: true`, update image repository to the new custom image

## 6. Docker Compose Updates

- [x] 6.1 Update `docker-compose.yml` perplexity-mcp service to use the new image (build from `perplexity-mcp/`) with `BACKEND_URL` env var
- [x] 6.2 Remove `USE_PERPLEXITY` and `PERPLEXITY_API_KEY` env vars from docker-compose, keep `PERPLEXITY_URL` on worker

## 7. CI Pipeline

- [x] 7.1 Add `build-perplexity-mcp` job to `.github/workflows/build.yml` — builds and pushes the Perplexity MCP image from `perplexity-mcp/Dockerfile`
- [x] 7.2 Add `build-perplexity-mcp` to the `helm` job's `needs` list

## 8. Testing and Verification

- [x] 8.1 Run full backend test suite and fix any failures
- [x] 8.2 Run full frontend test suite (platform list should now include Perplexity) and fix any failures
- [x] 8.3 Test locally with `docker compose up --build`: verify Perplexity appears in Integrations, credential save/verify flow works, and worker picks up credentials for task execution
