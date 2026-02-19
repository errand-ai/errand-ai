## MODIFIED Requirements

### Requirement: Build on push to main
The CI workflow SHALL build and push images named `errand-backend` and `errand-task-runner` to the container registry. The Helm chart SHALL be built from `helm/errand/` and pushed as `errand-<version>.tgz`.

#### Scenario: Main branch image names
- **WHEN** a commit is pushed to `main`
- **THEN** images are pushed as `ghcr.io/<owner>/errand-backend:<version>` and `ghcr.io/<owner>/errand-task-runner:<version>`

#### Scenario: Chart packaging path
- **WHEN** the CI chart build step runs
- **THEN** it runs `helm dependency build helm/errand` and `helm package helm/errand`
