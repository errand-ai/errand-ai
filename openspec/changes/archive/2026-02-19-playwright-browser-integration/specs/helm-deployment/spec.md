## MODIFIED Requirements

### Requirement: Container image references are configurable

The Helm chart SHALL allow overriding the image repository and tag for frontend, backend/worker, task-runner, and Playwright MCP images via values. The `playwrightMcp.image.repository` and `playwrightMcp.image.tag` SHALL be set directly in values — the tag does NOT default to chart `appVersion` since the Playwright MCP image uses the official Microsoft release cycle (not the application version).

#### Scenario: Custom image tag

- **WHEN** `image.tag` is set to `0.2.0`
- **THEN** all deployments use that image tag

#### Scenario: Default Playwright MCP image

- **WHEN** the chart is installed with default values
- **THEN** the worker container's `PLAYWRIGHT_MCP_IMAGE` env var uses `mcr.microsoft.com/playwright/mcp:latest`

#### Scenario: Custom Playwright MCP image tag

- **WHEN** `playwrightMcp.image.tag` is set to `v1.2.0` in values
- **THEN** the worker container's `PLAYWRIGHT_MCP_IMAGE` env var uses `v1.2.0` as the tag

## ADDED Requirements

### Requirement: Playwright MCP values section in Helm chart

The Helm chart `values.yaml` SHALL include a `playwrightMcp` section with the following defaults:

- `image.repository`: `mcr.microsoft.com/playwright/mcp`
- `image.tag`: `"latest"`
- `memoryLimit`: `512m`
- `port`: `8931`
- `startupTimeout`: `30`

#### Scenario: Default values provide Playwright configuration

- **WHEN** the chart is installed with default values
- **THEN** the worker deployment receives environment variables for `PLAYWRIGHT_MCP_IMAGE`, `PLAYWRIGHT_MEMORY_LIMIT`, `PLAYWRIGHT_PORT`, and `PLAYWRIGHT_STARTUP_TIMEOUT` with the default values

### Requirement: Worker deployment includes Playwright environment variables

The Helm chart worker Deployment SHALL include environment variables that configure the Playwright MCP sidecar:

- `PLAYWRIGHT_MCP_IMAGE`: Set to `{{ .Values.playwrightMcp.image.repository }}:{{ .Values.playwrightMcp.image.tag }}`
- `PLAYWRIGHT_MEMORY_LIMIT`: Set to `{{ .Values.playwrightMcp.memoryLimit }}`
- `PLAYWRIGHT_PORT`: Set to `{{ .Values.playwrightMcp.port }}`
- `PLAYWRIGHT_STARTUP_TIMEOUT`: Set to `{{ .Values.playwrightMcp.startupTimeout }}`

#### Scenario: Worker receives Playwright configuration

- **WHEN** the Helm chart is deployed
- **THEN** the worker container has `PLAYWRIGHT_MCP_IMAGE`, `PLAYWRIGHT_MEMORY_LIMIT`, `PLAYWRIGHT_PORT`, and `PLAYWRIGHT_STARTUP_TIMEOUT` environment variables set from values
