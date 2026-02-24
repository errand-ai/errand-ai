## Context

Perplexity web search is currently provided to the task runner via a sidecar MCP server pod. The API key is managed as a deploy-time Kubernetes Secret referenced in Helm values (`perplexity.existingSecret`). The platform credential system now supports encrypted storage, admin UI management, and a verification flow. This change moves the Perplexity API key into that system.

Current architecture:
- K8s Secret → Helm `existingSecret` → `envFrom` on Perplexity deployment
- Worker checks `USE_PERPLEXITY` env var → injects MCP config with `$PERPLEXITY_URL`
- Conditional rendering: deployment + service only created when `existingSecret` is set

Target architecture:
- Admin enters API key via Integrations UI → encrypted in DB
- Perplexity sidecar always deployed → entrypoint fetches key from backend API
- Worker checks platform credentials in DB → injects MCP config if credentials exist

## Goals / Non-Goals

**Goals:**
- Manage Perplexity API key through the admin UI like other platform credentials
- Build a reusable pattern for future MCP tool providers (Brave Search, Fetch, etc.)
- Eliminate the deploy-time K8s Secret dependency for Perplexity
- Keep the sidecar MCP server architecture (worker connects via HTTP as before)

**Non-Goals:**
- Generalising the sidecar deployment mechanism (each tool provider gets its own Helm template for now)
- Credential rotation without pod restart (v1 requires restart to pick up new keys)
- Building Brave Search or Fetch integrations (just the pattern)
- Changing how the task runner connects to MCP servers

## Decisions

### 1. Add TOOL_PROVIDER to PlatformCapability

**Decision: New enum value, no interface changes**

Add `TOOL_PROVIDER = "tool_provider"` to `PlatformCapability`. This distinguishes agent tool providers from messaging platforms in the UI. The `Platform` base class is unchanged — tool providers simply don't implement `post()`, `delete_post()`, or `get_post()` (they already raise `NotImplementedError` by default).

Alternative considered: A separate `ToolProvider` base class — rejected as it would duplicate the credential infrastructure for no benefit.

### 2. Internal credentials endpoint for sidecar pods

**Decision: Unauthenticated cluster-internal endpoint at `/api/internal/credentials/{platform_id}`**

A new endpoint returns decrypted credentials for a given platform_id. It is not exposed via ingress (no `/api/internal` route in the ingress configuration). Security relies on Kubernetes network isolation — only pods in the same namespace can reach the backend ClusterIP service.

The endpoint returns `{"api_key": "pplx-..."}` if credentials exist, or HTTP 404 if not.

Alternative considered: Sharing `CREDENTIAL_ENCRYPTION_KEY` + `DATABASE_URL` with the sidecar so it queries the DB directly — rejected as it couples the sidecar to the backend's DB schema and crypto implementation.

### 3. Custom Perplexity MCP Docker image

**Decision: Node.js image with npm install at build time, shell entrypoint at runtime**

```
perplexity-mcp/
  Dockerfile        # FROM node:22-slim, npm install @perplexity-ai/mcp-server
  package.json      # depends on @perplexity-ai/mcp-server
  entrypoint.sh     # fetch key from backend, export, exec npm run start:http:public
```

The entrypoint:
1. Polls `GET $BACKEND_URL/api/internal/credentials/perplexity` every 30 seconds
2. If 404 (no credentials): log "No Perplexity API key configured. Waiting..." and retry
3. If 200: extract `api_key`, set `PERPLEXITY_API_KEY`, exec `npm run start:http:public`

Using `npm install` at build time (not `npx` at runtime) ensures the package is pre-installed in the image. `npm run start:http:public` uses the package's built-in HTTP mode with `BIND_ADDRESS=0.0.0.0`.

Alternative considered: Continuing to use the official `quay.io/devops_consultants/perplexity-mcp-server` image — rejected because it requires the API key as an env var at container start, with no mechanism to fetch it from an external source.

### 4. Helm deployment: always-on, no secret gating

**Decision: Remove conditional rendering, add BACKEND_URL env var**

The Perplexity deployment and service templates drop the `{{- if .Values.perplexity.existingSecret }}` conditional. The deployment always runs. Instead of `envFrom` referencing a K8s Secret, the container gets a `BACKEND_URL` env var pointing to the backend service. The entrypoint handles the "no credentials yet" case gracefully.

Remove `perplexity.existingSecret` from `values.yaml`. The `perplexity.image` values change to point to the new custom image (built from `perplexity-mcp/`). Add `perplexity.enabled` toggle (default `true`) so the deployment can still be disabled entirely.

### 5. Worker credential check

**Decision: Load platform credentials from DB via `load_credentials()`**

The worker already has a DB session. Instead of checking `USE_PERPLEXITY` env var, it calls `load_credentials("perplexity", session)`. If credentials exist, it injects the Perplexity MCP server URL (constructed from the Helm-configured `PERPLEXITY_URL` env var, which remains). The `USE_PERPLEXITY` env var and the env var check are removed.

The Perplexity URL itself stays as an env var (`PERPLEXITY_URL`) because it's an internal service URL determined by Helm, not a user credential.

### 6. Credential verification

**Decision: Test API call to Perplexity**

`PerplexityPlatform.verify_credentials()` makes a minimal API call to the Perplexity API (e.g., a simple chat completion with minimal tokens) to verify the key is valid. This follows the same pattern as `TwitterPlatform.verify_credentials()`.

## Risks / Trade-offs

- **Startup delay**: The Perplexity sidecar polls for credentials at startup. If no key is configured, it retries every 30 seconds. First task after key entry may need to wait up to 30 seconds. → Acceptable for a configuration-time operation.
- **Credential changes require pod restart**: If the admin rotates the API key, the sidecar still has the old key. → Acceptable for v1. Document in the UI or platform info.
- **Backend must be running first**: The sidecar depends on the backend being available to fetch credentials. → The backend has readiness probes; the sidecar's retry loop handles transient unavailability.
- **Internal endpoint security**: `/api/internal/credentials/{platform_id}` returns decrypted secrets with no auth. → Mitigated by K8s network isolation (ClusterIP, not in ingress). Same pattern as many internal service-to-service APIs.
