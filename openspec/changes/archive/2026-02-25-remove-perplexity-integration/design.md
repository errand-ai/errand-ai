## Context

The Perplexity integration was added in two changes (deploy-perplexity-mcp, perplexity-platform-integration) and consists of:

1. A standalone `perplexity-mcp` container (Node.js, runs `@perplexity-ai/mcp-server`) deployed as a K8s Deployment+Service and docker-compose service
2. A `PerplexityPlatform` class with `TOOL_PROVIDER` capability and an internal credentials endpoint (`/api/internal/credentials/perplexity`) that the sidecar polls to get the API key
3. Worker logic that conditionally injects `perplexity-ask` into the task-runner's MCP config and appends web search instructions to the system prompt
4. A CI job (`build-perplexity-mcp`) that builds and pushes the sidecar image
5. Two dedicated specs (`perplexity-platform`, `perplexity-mcp-deployment`) and references in three others

This will be replaced by a different approach in a future change, so we are doing a clean removal now.

## Goals / Non-Goals

**Goals:**
- Completely remove all Perplexity-specific code, configuration, and deployment resources
- Remove the `TOOL_PROVIDER` platform capability (only used by Perplexity)
- Update specs to reflect the removal
- Keep the platform abstraction (`platforms/base.py`, `platforms/__init__.py`) intact for other integrations (GitHub)

**Non-Goals:**
- Replacing Perplexity with an alternative web search capability (future change)
- Removing the platform credentials system (still used by GitHub)
- Removing the `/api/internal/credentials/{platform_id}` endpoint pattern (only remove the Perplexity-specific usage; the endpoint itself is generic but currently only used by Perplexity — remove it since no other consumer exists)
- Cleaning up archived change directories

## Decisions

### 1. Remove the internal credentials endpoint entirely
The `/api/internal/credentials/{platform_id}` endpoint was built solely for the Perplexity MCP sidecar's polling pattern. No other consumer uses it. Remove it rather than leaving dead code. If a future integration needs it, it can be re-added.

### 2. Remove TOOL_PROVIDER capability enum value
`TOOL_PROVIDER` was added exclusively for `PerplexityPlatform`. No other platform uses it. Remove the enum value from `PlatformCapability` to avoid dead code. The `SOCIAL_POSTING` and `SOURCE_CONTROL` values remain for Twitter and GitHub.

### 3. Delete the perplexity-mcp directory entirely
The `perplexity-mcp/` directory (Dockerfile, entrypoint.sh, package.json) is self-contained and has no shared code. Delete the entire directory.

### 4. Remove PERPLEXITY_API_KEY from .env
The `.env` file contains a Perplexity API key that is no longer needed. Remove it.

## Risks / Trade-offs

- **[Breaking for users with stored Perplexity credentials]** → Users who configured Perplexity API keys via the platform credentials UI will lose that configuration. Acceptable since the feature is being replaced.
- **[ArgoCD deployment needs perplexity values removed]** → The ArgoCD values file (`~/github/argocd/apps/content-manager-rancher-values.yaml`) may have `perplexity:` overrides. These should be removed or ArgoCD will pass orphaned values. Not in scope for code changes but note for deployment.
- **[Database rows remain]** → `platform_credentials` rows for `platform_id='perplexity'` will remain in the DB. Harmless — no code reads them.
