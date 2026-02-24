## ADDED Requirements

### Requirement: PerplexityPlatform class
The system SHALL provide a `PerplexityPlatform` class in `backend/platforms/perplexity.py` that extends `Platform`. The `info()` method SHALL return a `PlatformInfo` with `id="perplexity"`, `label="Perplexity"`, `capabilities={PlatformCapability.TOOL_PROVIDER}`, and `credential_schema=[{"key": "api_key", "label": "API Key", "type": "password", "required": True}]`. The `verify_credentials()` method SHALL make a minimal API call to the Perplexity API to validate the provided `api_key`.

#### Scenario: PerplexityPlatform info
- **WHEN** `PerplexityPlatform().info()` is called
- **THEN** it returns PlatformInfo with id "perplexity", label "Perplexity", capabilities containing TOOL_PROVIDER, and a credential schema with one required password field "api_key"

#### Scenario: Valid API key verification
- **WHEN** `verify_credentials({"api_key": "<valid-key>"})` is called with a valid Perplexity API key
- **THEN** the method returns `True`

#### Scenario: Invalid API key verification
- **WHEN** `verify_credentials({"api_key": "invalid-key"})` is called with an invalid key
- **THEN** the method raises an exception or returns `False` with an error message

### Requirement: PerplexityPlatform registered at startup
The backend SHALL register a `PerplexityPlatform` instance in the global `PlatformRegistry` during application startup, alongside existing platforms (Twitter, Slack).

#### Scenario: Perplexity available in platform list
- **WHEN** an authenticated user requests `GET /api/platforms`
- **THEN** the response includes a platform entry with id "perplexity" and capability "tool_provider"

### Requirement: Internal credentials endpoint
The backend SHALL expose `GET /api/internal/credentials/{platform_id}` without authentication. The endpoint SHALL load decrypted credentials for the given `platform_id` from the database using `load_credentials()`. If credentials exist, the endpoint SHALL return HTTP 200 with the decrypted credential dict as JSON. If no credentials exist, the endpoint SHALL return HTTP 404 with `{"detail": "No credentials configured"}`. This endpoint SHALL NOT be exposed via the Kubernetes ingress (no `/api/internal` path routing).

#### Scenario: Credentials exist
- **WHEN** a request is made to `GET /api/internal/credentials/perplexity` and Perplexity credentials are stored
- **THEN** the response is HTTP 200 with `{"api_key": "<decrypted-key>"}`

#### Scenario: No credentials configured
- **WHEN** a request is made to `GET /api/internal/credentials/perplexity` and no credentials are stored
- **THEN** the response is HTTP 404 with `{"detail": "No credentials configured"}`

#### Scenario: Unknown platform
- **WHEN** a request is made to `GET /api/internal/credentials/nonexistent`
- **THEN** the response is HTTP 404 with `{"detail": "Platform 'nonexistent' not found"}`

### Requirement: Perplexity MCP Docker image
A custom Docker image SHALL be built from `perplexity-mcp/Dockerfile`. The image SHALL use `node:22-slim` as the base. The build stage SHALL `npm install` the `@perplexity-ai/mcp-server` package. The image SHALL copy an `entrypoint.sh` script and set it as the container entrypoint.

#### Scenario: Image contains pre-installed package
- **WHEN** the Docker image is built
- **THEN** the `@perplexity-ai/mcp-server` package is installed in `node_modules/` and available for `npm run start:http:public`

### Requirement: Perplexity MCP entrypoint script
The `entrypoint.sh` script SHALL poll `GET $BACKEND_URL/api/internal/credentials/perplexity` in a loop. If the response is HTTP 200, the script SHALL extract the `api_key` value, export it as `PERPLEXITY_API_KEY`, and exec `npm run start:http:public`. If the response is HTTP 404 or a connection error, the script SHALL log "No Perplexity API key configured. Retrying in 30s..." to stderr and sleep 30 seconds before retrying. The `BACKEND_URL` environment variable SHALL be required.

#### Scenario: API key available at startup
- **WHEN** the container starts and `GET $BACKEND_URL/api/internal/credentials/perplexity` returns HTTP 200 with `{"api_key": "pplx-..."}`
- **THEN** the entrypoint exports `PERPLEXITY_API_KEY=pplx-...` and starts the MCP server in HTTP mode on port 8080

#### Scenario: No API key configured
- **WHEN** the container starts and `GET $BACKEND_URL/api/internal/credentials/perplexity` returns HTTP 404
- **THEN** the entrypoint logs "No Perplexity API key configured. Retrying in 30s..." and retries after 30 seconds

#### Scenario: Backend unavailable at startup
- **WHEN** the container starts and the backend is not yet ready (connection refused)
- **THEN** the entrypoint logs the error and retries after 30 seconds
