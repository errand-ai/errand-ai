## ADDED Requirements

### Requirement: Claude task-runner Dockerfile
The repository SHALL include a `task-runner/Dockerfile.claude` that produces a container image extending the base task-runner image with the Claude Code CLI. The Dockerfile SHALL take the base image as a build arg (`BASE_IMAGE`, default `errand-task-runner:latest`) and SHALL install `@anthropic-ai/claude-code` in a `node:24` builder stage, copying the resulting package into the final image. The base image's entrypoint, non-root user, and `WORKDIR` SHALL be unchanged. A `claude` executable SHALL be available on the PATH.

The package SHALL NOT be installed at runtime: the base image's entrypoint deletes pip and npm before the agent starts, by design.

#### Scenario: Image builds successfully
- **WHEN** `docker build -f task-runner/Dockerfile.claude -t claude-task-runner .` is run from the repository root
- **THEN** the image builds without errors and is tagged `claude-task-runner`

#### Scenario: Claude CLI is available
- **WHEN** the claude-task-runner container runs `claude --version`
- **THEN** the command exits 0 and prints the pinned Claude Code version string

#### Scenario: No package managers in the final image
- **WHEN** the claude-task-runner container runs `command -v npm` and `command -v pip`
- **THEN** neither command resolves to an executable

#### Scenario: Base task-runner functionality preserved
- **WHEN** the claude-task-runner container starts with standard task-runner environment variables and no Claude token
- **THEN** the Python agent loop (`/app/main.py`) executes normally

#### Scenario: Non-root execution
- **WHEN** the claude-task-runner container starts
- **THEN** the process runs as the `nonroot` user (UID 65532)

### Requirement: POSIX shell staged for the Claude Bash tool
The claude-task-runner image SHALL provide a `bash` executable and the shared libraries it requires, staged from a Debian builder stage using the same pattern the base image uses for `git`, `curl`, and `jq`. Claude Code rejects the base image's busybox `sh` and fails every Bash tool call with "No suitable shell found" — setting the `SHELL` environment variable does not change this. The default (non-claude) task-runner image SHALL NOT gain bash.

#### Scenario: bash present and executable
- **WHEN** the claude-task-runner container runs `bash -c 'echo $BASH_VERSION'`
- **THEN** the command exits 0 and prints a bash version string

#### Scenario: Bash tool executes a command
- **WHEN** Claude Code running in the claude-task-runner image invokes its Bash tool with `echo hello`
- **THEN** the tool result reports `is_error: false` and contains `hello`

#### Scenario: Default image unchanged
- **WHEN** the default `errand-task-runner` image runs `command -v bash`
- **THEN** the command does not resolve to an executable

### Requirement: Auto-update disabled in the image
The claude-task-runner image SHALL set `DISABLE_AUTOUPDATER=1` so the CLI does not attempt to replace itself at runtime. The image has no package managers and pins an exact CLI version; a self-update would defeat both.

#### Scenario: Autoupdater disabled
- **WHEN** the claude-task-runner container runs `claude doctor`
- **THEN** the output does not report auto-updates as enabled

### Requirement: Claude CLI version pinning
The Dockerfile SHALL pin `@anthropic-ai/claude-code` to an exact version via a Docker build arg (`CLAUDE_CODE_VERSION`) with a default value recorded in the Dockerfile. The stream-json event schema is not a stable API, so the transformer's fixtures SHALL be captured from the pinned version.

#### Scenario: Default version installs
- **WHEN** `docker build -f task-runner/Dockerfile.claude` is run without build args
- **THEN** the pinned default version of the CLI is installed

#### Scenario: Custom version override
- **WHEN** `docker build --build-arg CLAUDE_CODE_VERSION=2.1.220 -f task-runner/Dockerfile.claude` is run
- **THEN** CLI version 2.1.220 is installed and `claude --version` reports it

### Requirement: Per-architecture native binary
The `@anthropic-ai/claude-code` package resolves a platform-specific native binary (for example `@anthropic-ai/claude-code-linux-arm64`) rather than shipping portable JavaScript. The builder stage SHALL therefore resolve the package for the image's target architecture, and the build SHALL NOT copy one architecture's installed package into an image of another architecture.

#### Scenario: arm64 image carries an arm64 binary
- **WHEN** the image is built for `linux/arm64`
- **THEN** `claude --version` succeeds inside a `linux/arm64` container

#### Scenario: amd64 image carries an amd64 binary
- **WHEN** the image is built for `linux/amd64`
- **THEN** `claude --version` succeeds inside a `linux/amd64` container

### Requirement: CI builds claude-task-runner image
The CI pipeline SHALL build and push the `claude-task-runner` image alongside the existing images, using the same version tag derived from the `VERSION` file and the same registry (GHCR). The build SHALL cover the same architectures as the default task-runner image.

#### Scenario: CI builds the claude image
- **WHEN** a build on `main` is triggered for version `X.Y.Z`
- **THEN** `claude-task-runner:X.Y.Z` is built and pushed alongside `errand-task-runner:X.Y.Z`

#### Scenario: PR builds include claude image
- **WHEN** a PR build is triggered
- **THEN** the claude-task-runner image is tagged with the same PR pre-release version as the other images
