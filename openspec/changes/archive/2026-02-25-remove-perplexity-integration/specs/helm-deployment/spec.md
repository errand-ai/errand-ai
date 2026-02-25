## REMOVED Requirements

### Requirement: Perplexity MCP deployment
**Reason**: Perplexity integration removed; sidecar container no longer deployed
**Migration**: Delete `perplexity-deployment.yaml` template and remove `perplexity:` section from `values.yaml`

#### Scenario: No Perplexity deployment
- **WHEN** the Helm chart is deployed
- **THEN** no Perplexity MCP Deployment exists

### Requirement: Perplexity MCP Service
**Reason**: Perplexity integration removed; no service needed
**Migration**: Delete `perplexity-service.yaml` template

#### Scenario: No Perplexity service
- **WHEN** the Helm chart is deployed
- **THEN** no Perplexity MCP Service exists

### Requirement: Worker Perplexity environment variables
**Reason**: Perplexity integration removed; worker no longer needs PERPLEXITY_URL
**Migration**: Remove `PERPLEXITY_URL` env var from worker deployment template

#### Scenario: No Perplexity env vars on worker
- **WHEN** the worker container starts
- **THEN** `PERPLEXITY_URL` is not present in the container environment variables
