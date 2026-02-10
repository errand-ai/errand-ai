## ADDED Requirements

### Requirement: Build task runner image
The CI workflow SHALL include a `build-task-runner` job that builds the task runner Docker image from `task-runner/Dockerfile` and pushes it to the container registry. The job SHALL run in parallel with `build-frontend` and `build-backend`, depending on the `version` and `test` jobs. The image SHALL be tagged with the version from the `VERSION` file (same scheme as frontend and backend images). The image SHALL be pushed to `ghcr.io/<repository>-task-runner`.

#### Scenario: Main branch build
- **WHEN** a commit is pushed to `main` and tests pass
- **THEN** the task runner image is built and pushed with the tag from the `VERSION` file (e.g. `0.10.0`)

#### Scenario: PR build
- **WHEN** a PR is created and tests pass
- **THEN** the task runner image is built and pushed with a PR-specific tag (e.g. `0.10.0-pr9`)

#### Scenario: Multi-architecture build
- **WHEN** the task runner image is built
- **THEN** it is built for both `linux/amd64` and `linux/arm64` platforms

### Requirement: Helm job depends on task runner build
The `helm` job SHALL depend on `build-task-runner` in addition to `build-frontend` and `build-backend`. The Helm chart SHALL not be packaged until all three images have been successfully built and pushed.

#### Scenario: All builds succeed
- **WHEN** `build-frontend`, `build-backend`, and `build-task-runner` all succeed
- **THEN** the `helm` job runs and packages the chart

#### Scenario: Task runner build fails
- **WHEN** `build-task-runner` fails
- **THEN** the `helm` job does not run
