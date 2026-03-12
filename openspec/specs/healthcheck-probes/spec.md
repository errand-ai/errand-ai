## ADDED Requirements

### Requirement: Worker health HTTP endpoint
The worker process SHALL expose an HTTP health endpoint on a configurable port (default 8080, controlled by `HEALTH_PORT` environment variable). The endpoint SHALL be served by a background daemon thread started before the main poll loop.

#### Scenario: Worker is healthy
- **WHEN** a GET request is made to `/health` on the worker health port
- **AND** the worker has not received a shutdown signal
- **THEN** the endpoint SHALL return HTTP 200 with body `{"status": "ok"}`

#### Scenario: Worker is shutting down
- **WHEN** a GET request is made to `/health` on the worker health port
- **AND** the worker has received a shutdown signal (SIGTERM)
- **THEN** the endpoint SHALL return HTTP 503 with body `{"status": "shutting_down"}`

#### Scenario: Health port configuration
- **WHEN** the `HEALTH_PORT` environment variable is set to a valid port number
- **THEN** the worker health endpoint SHALL listen on that port instead of the default 8080

### Requirement: Server Kubernetes probes
The Helm server deployment template SHALL include httpGet liveness and readiness probes targeting the existing `/api/health` endpoint on port 8000.

#### Scenario: Server liveness probe configured
- **WHEN** the server deployment is rendered by Helm
- **THEN** the server container SHALL have a livenessProbe with `httpGet` on path `/api/health`, port 8000, with `initialDelaySeconds: 10`, `periodSeconds: 15`, `timeoutSeconds: 5`, `failureThreshold: 3`

#### Scenario: Server readiness probe configured
- **WHEN** the server deployment is rendered by Helm
- **THEN** the server container SHALL have a readinessProbe with `httpGet` on path `/api/health`, port 8000, with `initialDelaySeconds: 5`, `periodSeconds: 15`, `timeoutSeconds: 5`, `failureThreshold: 3`

### Requirement: Worker Kubernetes probes
The Helm worker deployment template SHALL include httpGet liveness and readiness probes targeting the worker health endpoint.

#### Scenario: Worker liveness probe configured
- **WHEN** the worker deployment is rendered by Helm
- **THEN** the worker container SHALL have a livenessProbe with `httpGet` on path `/health`, port matching `worker.healthPort` value, with `initialDelaySeconds: 10`, `periodSeconds: 15`, `timeoutSeconds: 5`, `failureThreshold: 3`

#### Scenario: Worker readiness probe configured
- **WHEN** the worker deployment is rendered by Helm
- **THEN** the worker container SHALL have a readinessProbe with `httpGet` on path `/health`, port matching `worker.healthPort` value, with `initialDelaySeconds: 5`, `periodSeconds: 15`, `timeoutSeconds: 5`, `failureThreshold: 3`

#### Scenario: Worker health port exposed
- **WHEN** the worker deployment is rendered by Helm
- **THEN** the worker container SHALL have an `env` entry `HEALTH_PORT` set to `.Values.worker.healthPort`

### Requirement: Docker Compose server healthcheck
Both `testing/docker-compose.yml` and `deploy/docker-compose.yml` SHALL define a `healthcheck` on the errand server service.

#### Scenario: Server healthcheck in testing compose
- **WHEN** the testing docker-compose is used
- **THEN** the errand service SHALL have a healthcheck using python urllib to call `http://localhost:8000/api/health` with interval 10s, timeout 5s, retries 5

#### Scenario: Server healthcheck in deploy compose
- **WHEN** the deploy docker-compose is used
- **THEN** the errand service SHALL have a healthcheck using python urllib to call `http://localhost:8000/api/health` with interval 10s, timeout 5s, retries 5

### Requirement: Docker Compose worker healthcheck
Both `testing/docker-compose.yml` and `deploy/docker-compose.yml` SHALL define a `healthcheck` on the worker service.

#### Scenario: Worker healthcheck in testing compose
- **WHEN** the testing docker-compose is used
- **THEN** the worker service SHALL have a healthcheck using python urllib to call `http://localhost:8080/health` with interval 10s, timeout 5s, retries 5

#### Scenario: Worker healthcheck in deploy compose
- **WHEN** the deploy docker-compose is used
- **THEN** the worker service SHALL have a healthcheck using python urllib to call `http://localhost:8080/health` with interval 10s, timeout 5s, retries 5
