## MODIFIED Requirements

### Requirement: Server deployment template
The server deployment template SHALL include Kubernetes liveness and readiness probes for the server container, using httpGet against the `/api/health` endpoint.

#### Scenario: Probes rendered in server deployment
- **WHEN** the Helm chart is rendered with default values
- **THEN** the server container spec SHALL include `livenessProbe` and `readinessProbe` blocks with httpGet configuration

### Requirement: Worker deployment template
The worker deployment template SHALL include Kubernetes liveness and readiness probes for the worker container, expose the health port, and pass the `HEALTH_PORT` environment variable.

#### Scenario: Probes rendered in worker deployment
- **WHEN** the Helm chart is rendered with default values
- **THEN** the worker container spec SHALL include `livenessProbe` and `readinessProbe` blocks with httpGet configuration on the worker health port

### Requirement: Helm values defaults
The values.yaml SHALL include default probe configuration for both server and worker.

#### Scenario: Default health values present
- **WHEN** values.yaml is read
- **THEN** `worker.healthPort` SHALL default to `8080`
