## ADDED Requirements

### Requirement: Build Playwright MCP image

The CI workflow SHALL include a `build-playwright-mcp` job that builds the Playwright MCP Docker image from `playwright-mcp/Dockerfile` and pushes it to the container registry. The job SHALL run in parallel with `build-frontend`, `build-backend`, and `build-task-runner`, depending on the `version` and `test` jobs. The image SHALL be tagged with the version from the `VERSION` file (same scheme as other images). The image SHALL be pushed to `ghcr.io/<repository>-playwright-mcp`.

#### Scenario: Main branch build

- **WHEN** a commit is pushed to `main` and tests pass
- **THEN** the Playwright MCP image is built and pushed with the tag from the `VERSION` file (e.g. `0.43.0`)

#### Scenario: PR build

- **WHEN** a PR is created and tests pass
- **THEN** the Playwright MCP image is built and pushed with a PR-specific tag (e.g. `0.43.0-pr52`)

#### Scenario: Multi-architecture build

- **WHEN** the Playwright MCP image is built
- **THEN** it is built for both `linux/amd64` and `linux/arm64` platforms

## MODIFIED Requirements

### Requirement: Helm job depends on task runner build

The `helm` job SHALL depend on `build-task-runner` and `build-playwright-mcp` in addition to `build-frontend` and `build-backend`. The Helm chart SHALL not be packaged until all four images have been successfully built and pushed.

#### Scenario: All builds succeed

- **WHEN** `build-frontend`, `build-backend`, `build-task-runner`, and `build-playwright-mcp` all succeed
- **THEN** the `helm` job runs and packages the chart

#### Scenario: Playwright MCP build fails

- **WHEN** `build-playwright-mcp` fails
- **THEN** the `helm` job does not run
