## ADDED Requirements

### Requirement: Perplexity MCP Deployment gated by existingSecret

The Helm chart SHALL include a Deployment for the Perplexity MCP server, rendered only when `.Values.perplexity.existingSecret` is non-empty. The Deployment SHALL use the image `{{ .Values.perplexity.image.repository }}:{{ .Values.perplexity.image.tag }}` (defaulting to `mcp/perplexity-ask:latest`). The Deployment SHALL have a configurable `replicaCount` (default 1). The Deployment SHALL inject the referenced Secret via `envFrom.secretRef` so all keys in the Secret become environment variables in the container. The container SHALL expose port 8000.

#### Scenario: Perplexity deployed when secret is set

- **WHEN** `.Values.perplexity.existingSecret` is set to `"perplexity-api-key"`
- **THEN** the chart renders a Deployment named `<release>-perplexity-mcp` using the `mcp/perplexity-ask` image with `envFrom` referencing the `perplexity-api-key` Secret

#### Scenario: Perplexity not deployed when secret is empty

- **WHEN** `.Values.perplexity.existingSecret` is empty or not set
- **THEN** the chart does not render the Perplexity Deployment

#### Scenario: Custom image and replicas

- **WHEN** `.Values.perplexity.image.repository` is `"custom/perplexity"`, `.Values.perplexity.image.tag` is `"v1.0"`, and `.Values.perplexity.replicaCount` is `3`
- **THEN** the Deployment uses image `custom/perplexity:v1.0` with 3 replicas

### Requirement: Perplexity MCP Service

The Helm chart SHALL include a Service for the Perplexity MCP Deployment, rendered only when `.Values.perplexity.existingSecret` is non-empty. The Service SHALL target port 8000 and expose it on a configurable service port (default 8000). The Service SHALL select pods from the Perplexity Deployment.

#### Scenario: Service routes to Perplexity pods

- **WHEN** `.Values.perplexity.existingSecret` is set and the Perplexity Deployment has 2 replicas
- **THEN** the Service named `<release>-perplexity-mcp` load-balances across both pods on port 8000

#### Scenario: Service not rendered when secret is empty

- **WHEN** `.Values.perplexity.existingSecret` is empty or not set
- **THEN** the chart does not render the Perplexity Service
