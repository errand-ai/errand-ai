## Why

The task runner agent can use MCP servers configured through the admin settings UI, but these are manually configured per-deployment. Perplexity (web search) is a high-value MCP tool that should be available as a first-class, infrastructure-managed service — deployed alongside the application via the Helm chart, with zero manual configuration required.

## What Changes

- Add a new Helm value `.Values.perplexity.existingSecret` to conditionally deploy the Perplexity MCP server
- Create a Kubernetes Deployment for the `mcp/perplexity-ask` image (from Docker Hub), injecting the secret via `envFrom`
- Create a Kubernetes Service fronting the Perplexity deployment for stable in-cluster access
- Update the worker Deployment template to set `USE_PERPLEXITY=true` and `PERPLEXITY_URL=<service-url>` when the secret is configured
- Update the worker Python code to inject the `perplexity-ask` MCP server entry into `mcp.json` when `USE_PERPLEXITY=true`, using `$PERPLEXITY_URL` for env var substitution

## Capabilities

### New Capabilities
- `perplexity-mcp-deployment`: Helm templates for the Perplexity MCP server Deployment and Service, gated by `.Values.perplexity.existingSecret`

### Modified Capabilities
- `helm-deployment`: Add `.Values.perplexity` section and conditional `USE_PERPLEXITY`/`PERPLEXITY_URL` env vars on worker
- `task-worker`: Worker injects `perplexity-ask` server into `mcp.json` when `USE_PERPLEXITY=true`

## Impact

- **Helm chart**: New templates (`perplexity-deployment.yaml`, `perplexity-service.yaml`), updated `values.yaml`, updated `worker-deployment.yaml`
- **Worker code**: `process_task_in_container()` gains logic to merge a perplexity entry into `mcp_servers` before writing `mcp.json`
- **Dependencies**: `mcp/perplexity-ask` Docker Hub image (external); requires a pre-existing K8s Secret with the Perplexity API key
- **Backwards compatible**: When `.Values.perplexity.existingSecret` is unset (default), nothing changes
