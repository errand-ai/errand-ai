## MODIFIED Requirements

### Requirement: Build on push to main
GitHub Actions SHALL run a workflow on push to the `main` branch that runs all tests, then builds Docker images for frontend and backend, pushes them to the container registry, packages the Helm chart, and pushes it to the chart registry. The build jobs SHALL depend on tests passing.

#### Scenario: Main branch build
- **WHEN** a commit is pushed to `main`
- **THEN** tests run first, and only if they pass, Docker images are built and pushed with the tag from the `VERSION` file, and the Helm chart is packaged and pushed with the same version

### Requirement: Build on pull request
GitHub Actions SHALL run a workflow on pull request creation and update that runs all tests, then builds Docker images and pushes them with a PR-specific tag. The build jobs SHALL depend on tests passing. The Helm chart SHALL be packaged but not pushed to the chart registry.

#### Scenario: PR build tagging
- **WHEN** a PR numbered 42 is created and `VERSION` contains `0.1.0`
- **THEN** tests run first, and only if they pass, Docker images are built and pushed with tag `0.1.0-pr42`

#### Scenario: PR chart packaging
- **WHEN** a PR build runs
- **THEN** tests run first, and then the Helm chart is packaged (for validation) but not pushed to the chart registry

## ADDED Requirements

### Requirement: CI test job
The CI workflow SHALL include a `test` job that runs backend and frontend tests. This job SHALL install Python and Node.js, install test dependencies, and execute both test suites. The `build-frontend` and `build-backend` jobs SHALL depend on the `test` job succeeding.

#### Scenario: Tests pass and builds proceed
- **WHEN** the `test` job completes successfully
- **THEN** the `build-frontend` and `build-backend` jobs start

#### Scenario: Tests fail and builds are skipped
- **WHEN** the `test` job fails
- **THEN** the `build-frontend` and `build-backend` jobs do not run

#### Scenario: Test job runs both suites
- **WHEN** the `test` job executes
- **THEN** it runs `pytest` for backend tests and `npm test` for frontend tests, reporting results for both
