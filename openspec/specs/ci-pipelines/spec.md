## Requirements

### Requirement: Build on push to main
GitHub Actions SHALL run a workflow on push to the `main` branch that runs all tests, then builds the Docker image for the combined application (which includes frontend static assets) and the task runner, pushes them to the container registry, packages the Helm chart, and pushes it to the chart registry. The build jobs SHALL depend on tests passing.

#### Scenario: Main branch build
- **WHEN** a commit is pushed to `main`
- **THEN** tests run first, and only if they pass, the application image (including frontend assets) and task runner image are built and pushed with the tag from the `VERSION` file, and the Helm chart is packaged and pushed with the same version

### Requirement: Build on pull request
GitHub Actions SHALL run a workflow on pull request creation and update that runs all tests, then builds the application image (including frontend assets) and task runner image and pushes them with a PR-specific tag. The build jobs SHALL depend on tests passing. The Helm chart SHALL be packaged but not pushed to the chart registry.

#### Scenario: PR build tagging
- **WHEN** a PR numbered 42 is created and `VERSION` contains `0.1.0`
- **THEN** tests run first, and only if they pass, the application and task runner images are built and pushed with tag `0.1.0-pr42`

#### Scenario: PR chart packaging
- **WHEN** a PR build runs
- **THEN** tests run first, and then the Helm chart is packaged (for validation) but not pushed to the chart registry

### Requirement: Immutable version tags
The CI pipeline on main SHALL verify that the version tag does not already exist in the container registry before pushing. If the tag exists, the build SHALL fail. The check SHALL verify the `errand` and `errand-task-runner` image tags.

#### Scenario: Duplicate version detected
- **WHEN** the `VERSION` file contains `0.1.0` and tag `0.1.0` already exists in the registry for `errand` or `errand-task-runner`
- **THEN** the CI build fails with an error indicating the version must be incremented

#### Scenario: New version succeeds
- **WHEN** the `VERSION` file contains `0.2.0` and tag `0.2.0` does not exist
- **THEN** the CI build succeeds and pushes the tagged artifacts

### Requirement: Multi-stage Docker builds
The CI pipeline SHALL use a multi-stage Dockerfile for the application image: a Node.js stage to build the frontend assets, a Python build stage to install dependencies, and a slim Python runtime as the final stage. The Dockerfile SHALL copy source from `errand/` (not `backend/`). The task runner SHALL continue to use its own Dockerfile.

#### Scenario: Application image build
- **WHEN** the application Docker image is built
- **THEN** the final image contains the Python runtime, installed dependencies from `errand/requirements.txt`, application code from `errand/`, and the frontend static assets in a `static/` directory — but not Node.js, npm, or frontend source files

### Requirement: CI test job
The CI workflow SHALL include a `test` job that runs application and frontend tests. This job SHALL install Python and Node.js, install test dependencies, and execute both test suites. The `build-errand` and `build-task-runner` jobs SHALL depend on the `test` job succeeding. The application test working directory SHALL be `errand`.

#### Scenario: Tests pass and builds proceed
- **WHEN** the `test` job completes successfully
- **THEN** the `build-errand` and `build-task-runner` jobs start

#### Scenario: Tests fail and builds are skipped
- **WHEN** the `test` job fails
- **THEN** the `build-errand` and `build-task-runner` jobs do not run

#### Scenario: Test job runs both suites
- **WHEN** the `test` job executes
- **THEN** it runs `pytest` for application tests (working directory `errand`) and `npm test` for frontend tests, reporting results for both

### Requirement: Build Perplexity MCP image
The CI workflow SHALL include a `build-perplexity-mcp` job that builds the Docker image from `perplexity-mcp/Dockerfile` and pushes it to the container registry. The job SHALL depend on the `version` job. The image SHALL be tagged with the version from the `VERSION` file (same as other images). On pull requests, the image SHALL be tagged with the PR-specific tag (e.g., `0.4.0-pr5`). The `helm` job SHALL depend on `build-perplexity-mcp` in addition to the existing build jobs.

#### Scenario: Perplexity MCP image built on main push
- **WHEN** a commit is pushed to `main` and `VERSION` contains `0.5.0`
- **THEN** the Perplexity MCP image is built and pushed with tag `0.5.0`

#### Scenario: Perplexity MCP image built on PR
- **WHEN** PR #5 is created and `VERSION` contains `0.5.0`
- **THEN** the Perplexity MCP image is built and pushed with tag `0.5.0-pr5`

#### Scenario: Helm job waits for Perplexity MCP build
- **WHEN** the CI pipeline runs
- **THEN** the `helm` job depends on `build-perplexity-mcp` completing successfully

### Requirement: Helm job depends on image builds
The `helm` job SHALL depend on `build-errand`, `build-task-runner`, and `build-perplexity-mcp`. The Helm chart SHALL not be packaged until all images have been successfully built and pushed.

#### Scenario: All builds succeed
- **WHEN** `build-errand` and `build-task-runner` both succeed
- **THEN** the `helm` job runs and packages the chart

#### Scenario: Application build fails
- **WHEN** `build-errand` fails
- **THEN** the `helm` job does not run
