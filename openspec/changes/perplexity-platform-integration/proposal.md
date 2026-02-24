## Why

The Perplexity API key is currently a deploy-time secret managed via Helm values and a Kubernetes Secret. Now that the platform credential system supports encrypted storage and a UI for credential management, the Perplexity API key should be managed the same way as Twitter and Slack credentials — entered through the admin UI, encrypted in the database, and loaded at runtime. This eliminates the deploy-time dependency and makes Perplexity configuration self-service for admins.

## What Changes

- Add `TOOL_PROVIDER` to `PlatformCapability` enum to distinguish agent tool providers (Perplexity, future search providers) from messaging platforms (Twitter, Slack)
- Register a new `PerplexityPlatform` in the platform registry with a single credential field (`api_key`)
- Add an internal (cluster-only) API endpoint for sidecar pods to retrieve decrypted platform credentials
- Build a custom Docker image for the Perplexity MCP server that installs `@perplexity-ai/mcp-server` via npm and uses an entrypoint script to fetch the API key from the backend at startup
- Update the Helm chart to always deploy the Perplexity MCP sidecar (remove `existingSecret` gating)
- Update the worker to check platform credentials in the database instead of `USE_PERPLEXITY` environment variable
- Remove the `existingSecret`-based Perplexity deployment pattern from Helm

## Capabilities

### New Capabilities

- `perplexity-platform`: PerplexityPlatform class, internal credentials endpoint, custom Docker image with entrypoint, and CI pipeline for the image

### Modified Capabilities

- `platform-abstraction`: Add `TOOL_PROVIDER` to the `PlatformCapability` enum
- `task-worker`: Replace `USE_PERPLEXITY` env var check with platform credential lookup for Perplexity MCP injection
- `helm-deployment`: Perplexity deployment always-on, fetches API key from backend instead of K8s Secret
- `ci-pipelines`: Build the custom Perplexity MCP image alongside backend/frontend images

## Impact

- `backend/platforms/base.py` — add `TOOL_PROVIDER` capability
- `backend/platforms/perplexity.py` — new PerplexityPlatform class
- `backend/platforms/__init__.py` — register PerplexityPlatform
- `backend/main.py` — new internal credentials endpoint
- `backend/worker.py` — replace env var check with DB credential check
- `perplexity-mcp/` — new directory: Dockerfile, package.json, entrypoint.sh
- `helm/content-manager/templates/perplexity-*.yaml` — update deployment and remove existingSecret gating
- `helm/content-manager/values.yaml` — remove `perplexity.existingSecret`, add backend URL config
- `.github/workflows/build.yml` — add perplexity-mcp image build job
- `docker-compose.yml` — update perplexity service to use new image
