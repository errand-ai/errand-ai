## MODIFIED Requirements

### Requirement: Helm chart deploys all application components
The Helm chart name SHALL be `errand`. Template helper names SHALL use `errand.fullname` and `errand.labels`. The chart directory SHALL be `helm/errand/`. Image repositories SHALL default to `ghcr.io/devops-consultants/errand-backend` and `ghcr.io/devops-consultants/errand-task-runner`.

#### Scenario: Chart identity
- **WHEN** `helm show chart helm/errand/` is run
- **THEN** the chart name is `errand`

#### Scenario: Resource naming
- **WHEN** the chart is rendered with default values
- **THEN** Kubernetes resources use names prefixed with `errand` (e.g. `errand-backend`, `errand-worker`)
