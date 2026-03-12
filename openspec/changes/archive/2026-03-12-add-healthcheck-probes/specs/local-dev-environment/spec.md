## MODIFIED Requirements

### Requirement: Docker Compose service health monitoring
The errand server and worker services in both testing and deploy docker-compose files SHALL have healthcheck directives that verify the service is responsive.

#### Scenario: Errand server healthcheck defined
- **WHEN** docker-compose services are inspected
- **THEN** the errand service SHALL have a healthcheck that queries `http://localhost:8000/api/health`

#### Scenario: Worker healthcheck defined
- **WHEN** docker-compose services are inspected
- **THEN** the worker service SHALL have a healthcheck that queries `http://localhost:8080/health`
