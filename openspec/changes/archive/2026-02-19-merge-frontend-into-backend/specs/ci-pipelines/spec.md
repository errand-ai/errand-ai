## MODIFIED Requirements

### Requirement: Build on push to main
GitHub Actions SHALL run a workflow on push to the `main` branch that runs all tests, then builds the Docker image for the combined backend (which includes frontend static assets) and the task runner, pushes them to the container registry, packages the Helm chart, and pushes it to the chart registry. The build jobs SHALL depend on tests passing.

#### Scenario: Main branch build
- **WHEN** a commit is pushed to `main`
- **THEN** tests run first, and only if they pass, the backend image (including frontend assets) and task runner image are built and pushed with the tag from the `VERSION` file, and the Helm chart is packaged and pushed with the same version

### Requirement: Build on pull request
GitHub Actions SHALL run a workflow on pull request creation and update that runs all tests, then builds the backend image (including frontend assets) and task runner image and pushes them with a PR-specific tag. The build jobs SHALL depend on tests passing. The Helm chart SHALL be packaged but not pushed to the chart registry.

#### Scenario: PR build tagging
- **WHEN** a PR numbered 42 is created and `VERSION` contains `0.1.0`
- **THEN** tests run first, and only if they pass, the backend and task runner images are built and pushed with tag `0.1.0-pr42`

#### Scenario: PR chart packaging
- **WHEN** a PR build runs
- **THEN** tests run first, and then the Helm chart is packaged (for validation) but not pushed to the chart registry

### Requirement: Immutable version tags
The CI pipeline on main SHALL verify that the version tag does not already exist in the container registry before pushing. If the tag exists, the build SHALL fail. The check SHALL verify the backend and task runner image tags (not a frontend image, which no longer exists).

#### Scenario: Duplicate version detected
- **WHEN** the `VERSION` file contains `0.1.0` and tag `0.1.0` already exists in the registry
- **THEN** the CI build fails with an error indicating the version must be incremented

#### Scenario: New version succeeds
- **WHEN** the `VERSION` file contains `0.2.0` and tag `0.2.0` does not exist
- **THEN** the CI build succeeds and pushes the tagged artifacts

### Requirement: Multi-stage Docker builds
The CI pipeline SHALL use a multi-stage Dockerfile for the backend image: a Node.js stage to build the frontend assets, a Python build stage to install dependencies, and a slim Python runtime as the final stage. The task runner SHALL continue to use its own Dockerfile.

#### Scenario: Backend image build
- **WHEN** the backend Docker image is built
- **THEN** the final image contains the Python runtime, installed dependencies, and the frontend static assets in a `static/` directory — but not Node.js, npm, or frontend source files

### Requirement: CI test job
The CI workflow SHALL include a `test` job that runs backend and frontend tests. This job SHALL install Python and Node.js, install test dependencies, and execute both test suites. The `build-backend` and `build-task-runner` jobs SHALL depend on the `test` job succeeding.

#### Scenario: Tests pass and builds proceed
- **WHEN** the `test` job completes successfully
- **THEN** the `build-backend` and `build-task-runner` jobs start

#### Scenario: Tests fail and builds are skipped
- **WHEN** the `test` job fails
- **THEN** the `build-backend` and `build-task-runner` jobs do not run

#### Scenario: Test job runs both suites
- **WHEN** the `test` job executes
- **THEN** it runs `pytest` for backend tests and `npm test` for frontend tests, reporting results for both

### Requirement: Helm job depends on image builds
The `helm` job SHALL depend on `build-backend` and `build-task-runner`. The Helm chart SHALL not be packaged until both images have been successfully built and pushed.

#### Scenario: All builds succeed
- **WHEN** `build-backend` and `build-task-runner` both succeed
- **THEN** the `helm` job runs and packages the chart

#### Scenario: Backend build fails
- **WHEN** `build-backend` fails
- **THEN** the `helm` job does not run

## REMOVED Requirements

### Requirement: Frontend image build (implicit in "Multi-stage Docker builds" original scenario)
**Reason**: There is no longer a separate frontend Docker image. The frontend is built as a stage within the backend Dockerfile.
**Migration**: Remove the `build-frontend` job from the GitHub Actions workflow.

### Requirement: Helm job depends on task runner build
**Reason**: Replaced by updated "Helm job depends on image builds" requirement which lists both remaining images (backend and task runner) without referencing the removed frontend build.
**Migration**: Update `helm` job `needs` to reference only `build-backend` and `build-task-runner`.
