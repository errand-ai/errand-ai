## MODIFIED Requirements

### Requirement: Perplexity MCP deployment
The Helm chart SHALL include a Deployment for the Perplexity MCP server, rendered when `.Values.perplexity.enabled` is `true` (default). The Deployment SHALL use the image `{{ .Values.perplexity.image.repository }}:{{ .Values.perplexity.image.tag }}`. The Deployment SHALL have a configurable `replicaCount` (default 1). The container SHALL have a `BACKEND_URL` environment variable set to the backend service URL (`http://{{ include "content-manager.fullname" . }}-backend:{{ .Values.backend.service.port }}`). The container SHALL expose port 8080. The Deployment SHALL NOT reference any Kubernetes Secret via `envFrom`.

#### Scenario: Perplexity deployed by default
- **WHEN** the chart is deployed with default values (`.Values.perplexity.enabled` is `true`)
- **THEN** the chart renders a Perplexity Deployment with `BACKEND_URL` env var pointing to the backend service

#### Scenario: Perplexity disabled
- **WHEN** `.Values.perplexity.enabled` is set to `false`
- **THEN** the chart does not render the Perplexity Deployment or Service

#### Scenario: No secret reference
- **WHEN** the Perplexity Deployment is rendered
- **THEN** the container does not have `envFrom` referencing any Kubernetes Secret

### Requirement: Perplexity MCP Service
The Helm chart SHALL include a Service for the Perplexity MCP Deployment, rendered when `.Values.perplexity.enabled` is `true`. The Service SHALL target port 8080 and expose it on a configurable service port (default 8080). The Service SHALL select pods from the Perplexity Deployment.

#### Scenario: Service routes to Perplexity pods
- **WHEN** `.Values.perplexity.enabled` is `true` and the Perplexity Deployment has 2 replicas
- **THEN** the Service named `<release>-perplexity-mcp` load-balances across both pods on port 8080

#### Scenario: Service not rendered when disabled
- **WHEN** `.Values.perplexity.enabled` is set to `false`
- **THEN** the chart does not render the Perplexity Service

### Requirement: Worker Perplexity environment variables
The worker Deployment SHALL include a `PERPLEXITY_URL` environment variable set to the Perplexity MCP service URL (`http://{{ include "content-manager.fullname" . }}-perplexity-mcp:{{ .Values.perplexity.service.port }}/mcp`) when `.Values.perplexity.enabled` is `true`. The worker Deployment SHALL NOT include `USE_PERPLEXITY` environment variable.

#### Scenario: Worker has PERPLEXITY_URL when enabled
- **WHEN** `.Values.perplexity.enabled` is `true`
- **THEN** the worker container has `PERPLEXITY_URL` set to the Perplexity service URL

#### Scenario: Worker has no Perplexity env vars when disabled
- **WHEN** `.Values.perplexity.enabled` is `false`
- **THEN** the worker container does not have `PERPLEXITY_URL` or `USE_PERPLEXITY` environment variables
