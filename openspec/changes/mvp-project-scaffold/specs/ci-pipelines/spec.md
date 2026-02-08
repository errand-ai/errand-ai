## ADDED Requirements

### Requirement: Build on push to main
GitHub Actions SHALL run a workflow on push to the `main` branch that builds Docker images for frontend and backend, pushes them to the container registry, packages the Helm chart, and pushes it to the chart registry.

#### Scenario: Main branch build
- **WHEN** a commit is pushed to `main`
- **THEN** Docker images are built and pushed with the tag from the `VERSION` file, and the Helm chart is packaged and pushed with the same version

### Requirement: Build on pull request
GitHub Actions SHALL run a workflow on pull request creation and update that builds Docker images and pushes them with a PR-specific tag. The Helm chart SHALL be packaged but not pushed to the chart registry.

#### Scenario: PR build tagging
- **WHEN** a PR numbered 42 is created and `VERSION` contains `0.1.0`
- **THEN** Docker images are built and pushed with tag `0.1.0-pr42`

#### Scenario: PR chart packaging
- **WHEN** a PR build runs
- **THEN** the Helm chart is packaged (for validation) but not pushed to the chart registry

### Requirement: Version sourced from VERSION file
All CI workflows SHALL read the application version from a `VERSION` file at the repository root. This file SHALL contain a single semver string (e.g. `0.1.0`).

#### Scenario: Version file read
- **WHEN** the CI workflow starts
- **THEN** it reads the version from `VERSION` and uses it as the base tag for all artifacts

### Requirement: Immutable version tags
The CI pipeline on main SHALL verify that the version tag does not already exist in the container registry before pushing. If the tag exists, the build SHALL fail.

#### Scenario: Duplicate version detected
- **WHEN** the `VERSION` file contains `0.1.0` and tag `0.1.0` already exists in the registry
- **THEN** the CI build fails with an error indicating the version must be incremented

#### Scenario: New version succeeds
- **WHEN** the `VERSION` file contains `0.2.0` and tag `0.2.0` does not exist
- **THEN** the CI build succeeds and pushes the tagged artifacts

### Requirement: Multi-stage Docker builds
The CI pipeline SHALL use multi-stage Dockerfiles: Node build stage to nginx runtime for frontend, Python build stage to slim runtime for backend/worker.

#### Scenario: Frontend image build
- **WHEN** the frontend Docker image is built
- **THEN** the final image contains only nginx and the built static assets, not Node.js or source files

#### Scenario: Backend image build
- **WHEN** the backend Docker image is built
- **THEN** the final image contains only the Python runtime and installed dependencies, not build tools

### Requirement: Helm chart version matches application version
The Helm chart `version` and `appVersion` in `Chart.yaml` SHALL be set to the value from the `VERSION` file during CI packaging.

#### Scenario: Chart version set
- **WHEN** `VERSION` contains `0.3.0`
- **THEN** the packaged Helm chart has `version: 0.3.0` and `appVersion: "0.3.0"`
