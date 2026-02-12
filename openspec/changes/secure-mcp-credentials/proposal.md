## Why

MCP server configurations entered via the Settings UI are stored in the database as JSON. This JSON often contains sensitive credentials (e.g. API keys in HTTP headers). Storing secrets directly in the database settings is a security concern — they are visible in the UI, returned by the API, and lack the protections of proper secret management (K8s secrets, environment variables). Admins need a way to reference secrets by name while keeping the actual values in the worker's runtime environment.

## What Changes

- The worker will perform shell-style environment variable substitution on the `mcp_servers` JSON before writing it as `mcp.json` into the task runner container
- Substitution supports two syntaxes: `$VARIABLE_NAME` and `${VARIABLE_NAME}`
- Substitution is performed against the worker process's own environment variables (sourced from K8s secrets, ConfigMaps, etc.)
- If a referenced variable does not exist in the worker's environment, the placeholder is left as-is (no error, no empty replacement)
- Substitution operates on string values only — it walks the JSON structure and replaces within string values, not keys
- Example: `"x-litellm-api-key": "Bearer $OPENAI_API_KEY"` becomes `"x-litellm-api-key": "Bearer sk-1234..."` if `OPENAI_API_KEY` is set in the worker environment

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-worker`: Worker performs environment variable substitution on `mcp_servers` configuration before writing `mcp.json` to the container

## Impact

- **Backend**: `worker.py` — add substitution logic between reading `mcp_servers` from settings and serializing to `mcp.json`
- **Tests**: New unit tests for the substitution function (various patterns, missing vars, nested JSON, edge cases)
- **Deployment**: No changes required — worker already has access to K8s secrets via environment variables; admins just need to update their MCP configs to use placeholders
- **Settings UI/API**: No changes — the UI and API continue to store whatever JSON the admin enters, placeholders included
