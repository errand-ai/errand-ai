## ADDED Requirements

### Requirement: Custom task-runner image documentation
The repository SHALL include documentation at `task-runner/CUSTOM_IMAGES.md` explaining how to build a custom task-runner image by extending the base image. It SHALL include a working sample Dockerfile using the published base image, instructions for adding tools or dependencies, and compatibility guidance for the entrypoint and the structured event protocol.

#### Scenario: Documentation exists
- **WHEN** a user wants to create a custom task-runner image
- **THEN** `task-runner/CUSTOM_IMAGES.md` explains the base-image extension pattern

#### Scenario: Sample Dockerfile provided
- **WHEN** a user reads the custom image documentation
- **THEN** it contains a working example Dockerfile that extends the base task-runner image

### Requirement: Base image constraints documented
The custom image documentation SHALL state the constraints a derived image inherits, because they are not obvious and silently break common additions:

- the base is distroless; `/bin/sh` is busybox and there is no `bash`, so software that requires a POSIX shell it recognises must stage one
- pip and npm are removed — at build time as root for the interpreter's bootstrap surface, and by the entrypoint for the staged copies — so dependencies must be installed in a builder stage and copied in, never at runtime
- the image runs as `nonroot` (UID 65532) with `WORKDIR /workspace`
- the entrypoint (`/app/entrypoint.sh`) installs skill dependencies and then hands off to `/app/main.py`; a derived image that replaces the entrypoint loses skill dependency installation
- output must reach the runner's contract: structured events on stderr, `TaskRunnerOutput` on stdout, `/output/result.json`, and the result callback

#### Scenario: Shell constraint documented
- **WHEN** a user reads the custom image documentation
- **THEN** it states that the base provides busybox `sh` and no `bash`, and shows how to stage a shell if one is required

#### Scenario: Package manager constraint documented
- **WHEN** a user reads the custom image documentation
- **THEN** it states that pip and npm are unavailable at runtime and that dependencies must be copied from a builder stage

### Requirement: Delegation parity documented
The custom image documentation SHALL record which task-runner features do not apply when a task is delegated to the Claude Code CLI: context compaction, the stall guard, XML and Harmony tool-call recovery, the file-mutation queue and file tools, per-command timeouts, and mid-task Google Workspace token refresh.

#### Scenario: Parity gap listed
- **WHEN** an operator evaluates the claude image for a workload
- **THEN** the documentation lists the runner features unavailable on that path
