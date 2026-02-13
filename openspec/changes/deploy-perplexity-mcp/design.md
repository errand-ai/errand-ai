## Context

The worker processes tasks by spinning up a task runner container (via DinD sidecar) that uses an AI agent with MCP tool servers. MCP server configuration is stored in the `mcp_servers` admin setting as a JSON blob (`{"mcpServers": {...}}`), which the worker writes to `mcp.json` inside the container after performing `$VAR` environment variable substitution.

Currently, all MCP servers must be manually configured through the admin UI. Perplexity (web search) is a commonly-needed tool that could instead be deployed as infrastructure alongside the app, requiring only a Kubernetes Secret with the API key.

The Docker Hub image `mcp/perplexity-ask` provides an HTTP-based MCP server that exposes Perplexity's search API as an MCP tool.

## Goals / Non-Goals

**Goals:**

- Deploy the Perplexity MCP server as a K8s Deployment + Service, gated by a Helm value
- Automatically configure the worker to inject Perplexity into the task runner's MCP config
- Keep the feature fully opt-in — no behavioral change when the secret is not set

**Non-Goals:**

- Managing the Perplexity API key secret (must be pre-created externally, like other secrets)
- Adding Perplexity to the admin settings UI (it's infrastructure-managed, not user-configured)
- Supporting other MCP servers via the same pattern (can be generalized later if needed)

## Decisions

### 1. Conditional deployment via `existingSecret`

Follow the established pattern used by `database.existingSecret`, `keycloak.existingSecret`, and `openai.existingSecret`. When `.Values.perplexity.existingSecret` is non-empty, deploy the resources; otherwise, skip them entirely.

**Alternative**: A separate `perplexity.enabled` flag — rejected because the secret is the natural gate. If you have a secret, you want the deployment; no secret means nothing to deploy.

### 2. `envFrom` for secret injection

Use `envFrom.secretRef` on the Perplexity deployment rather than mapping individual keys. The `mcp/perplexity-ask` image may need various env vars (API key, config), and `envFrom` lets the secret define whatever the image requires without the chart needing to know the key names.

### 3. Worker-side MCP injection (not admin settings)

The worker checks `USE_PERPLEXITY` and `PERPLEXITY_URL` env vars and merges a `perplexity-ask` entry into the `mcp_servers` dict before writing `mcp.json`. This happens in the Python code, not as a Helm-level config injection.

**Why**: The `mcp_servers` setting comes from the database (admin UI), and the worker already applies `substitute_env_vars()` on it. Injecting the perplexity entry in Python means:
- It coexists with user-configured MCP servers from the admin UI
- The `$PERPLEXITY_URL` placeholder uses the existing env var substitution path
- No database changes needed

### 4. System prompt augmentation when Perplexity is enabled

When `USE_PERPLEXITY=true`, the worker appends a short instruction block to the system prompt before copying it into the container. This tells the LLM that it has access to the `perplexity-ask` MCP tool and when to use it (current information, web research, reasoning that needs context beyond training data).

**Why append, not prepend**: The admin-configured system prompt sets the primary persona and task context. Perplexity instructions are supplementary tooling guidance and belong at the end. Appending also avoids breaking any leading-context expectations the admin prompt may have.

**Why not a separate file**: The task runner already reads `system_prompt.txt` — adding a second file would require task runner changes. Appending to the existing prompt keeps the change contained to the worker.

### 5. Service URL format

The Perplexity service URL follows the standard K8s convention: `http://<release>-perplexity-mcp:<port>/sse`. The `/sse` path is the standard SSE transport endpoint for HTTP MCP servers. Port defaults to 8000 (standard for the `mcp/perplexity-ask` image).

## Risks / Trade-offs

- **Image availability**: `mcp/perplexity-ask` is a third-party Docker Hub image — if it's removed or changes API, the deployment breaks. → Mitigation: Pin a specific image tag in values rather than using `latest`.
- **Secret key names**: Using `envFrom` means the chart doesn't validate that the secret contains the right keys. → Mitigation: Document required secret keys; the pod will fail to start with clear errors if the API key is missing.
- **MCP config merge order**: If the admin also configures a `perplexity-ask` entry in the settings UI, the worker-injected entry would be overridden (or override, depending on merge order). → Decision: Worker-injected entry is added first, then admin settings are merged on top, so admin config wins if there's a conflict.
