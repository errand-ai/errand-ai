## ADDED Requirements

### Requirement: Claude task-runner Dockerfile
The repository SHALL include a `task-runner/Dockerfile.claude` that produces a container image extending the base task-runner with Node.js and the Claude Code CLI. The Dockerfile SHALL use the base `task-runner` image as a build stage or base layer. The final image SHALL include Node.js 22.x runtime and the `@anthropic-ai/claude-code` npm package installed globally. The `claude` binary SHALL be available on the PATH.

#### Scenario: Image builds successfully
- **WHEN** `docker build -f task-runner/Dockerfile.claude -t claude-task-runner task-runner/` is run
- **THEN** the image builds without errors and is tagged `claude-task-runner`

#### Scenario: Claude CLI is available
- **WHEN** the claude-task-runner container starts
- **THEN** `claude --version` executes successfully and outputs a Claude Code version string

#### Scenario: Node.js is available
- **WHEN** the claude-task-runner container starts
- **THEN** `node --version` executes successfully and outputs a v22.x version string

#### Scenario: Base task-runner functionality preserved
- **WHEN** the claude-task-runner container starts with standard task-runner environment variables
- **THEN** the Python agent loop (`/app/main.py`) executes normally as a fallback

#### Scenario: Non-root execution
- **WHEN** the claude-task-runner container starts
- **THEN** the process runs as the `nonroot` user (UID 65532)

### Requirement: Claude CLI version pinning
The Dockerfile SHALL pin the `@anthropic-ai/claude-code` package to a specific version via a Docker build arg (`CLAUDE_CODE_VERSION`) with a sensible default. This prevents unexpected breaking changes from upstream updates.

#### Scenario: Default version installs
- **WHEN** `docker build -f task-runner/Dockerfile.claude` is run without build args
- **THEN** the default pinned version of claude CLI is installed

#### Scenario: Custom version override
- **WHEN** `docker build --build-arg CLAUDE_CODE_VERSION=1.2.3 -f task-runner/Dockerfile.claude` is run
- **THEN** claude CLI version 1.2.3 is installed

### Requirement: CI builds claude-task-runner image
The CI pipeline SHALL build and push the `claude-task-runner` image alongside the default `task-runner` image. Both images SHALL use the same version tag from the `VERSION` file. The claude-task-runner image SHALL be pushed to the same container registry (GHCR) as the default image.

#### Scenario: CI builds both images
- **WHEN** a CI build is triggered
- **THEN** both `errand-task-runner:0.70.0` and `claude-task-runner:0.70.0` images are built and pushed

#### Scenario: PR builds include claude image
- **WHEN** a PR build is triggered
- **THEN** the claude-task-runner image is tagged with the PR version (e.g., `0.70.0-pr5`)
