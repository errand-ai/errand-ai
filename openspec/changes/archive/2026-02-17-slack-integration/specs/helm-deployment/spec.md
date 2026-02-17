## MODIFIED Requirements

### Requirement: Ingress path routing
The Helm ingress template SHALL include a `/slack` path with `Prefix` pathType that routes to the backend service. The path SHALL be ordered before the catch-all `/` path to ensure correct matching. The backend service port SHALL be the same as used for `/api` and `/auth` routes.

#### Scenario: Slack webhook routed to backend
- **WHEN** an external request arrives at `https://<domain>/slack/commands`
- **THEN** the ingress routes it to the backend service

#### Scenario: Ordering before catch-all
- **WHEN** the ingress template is rendered
- **THEN** the `/slack` path appears before the `/` catch-all path

#### Scenario: Existing routes unchanged
- **WHEN** the ingress template is rendered
- **THEN** `/api`, `/auth`, and `/mcp` routes remain unchanged
