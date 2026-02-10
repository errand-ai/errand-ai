## ADDED Requirements

### Requirement: Task runner Dockerfile
The repository SHALL include a `task-runner/Dockerfile` that produces a minimal, hardened container image for executing tasks inside DinD. The Dockerfile SHALL use a multi-stage build: the first stage copies the statically-linked busybox binary from `busybox:1.37-musl`, and the final stage uses `gcr.io/distroless/static-debian12:nonroot` as the base. The only executable in the final image SHALL be `/usr/local/bin/cat` (busybox binary renamed). The working directory SHALL be `/workspace`. The entrypoint SHALL be `["/usr/local/bin/cat", "/workspace/prompt.txt"]`.

#### Scenario: Image builds successfully
- **WHEN** `docker build -t task-runner task-runner/` is run
- **THEN** the image builds without errors and is tagged `task-runner`

#### Scenario: Image runs as non-root
- **WHEN** the task runner container starts
- **THEN** the process runs as the `nonroot` user (UID 65532)

#### Scenario: No shell available
- **WHEN** an attempt is made to execute `/bin/sh` inside the container
- **THEN** the command fails because no shell exists in the image

#### Scenario: No package manager available
- **WHEN** an attempt is made to run `apt-get`, `apk`, or any package manager inside the container
- **THEN** the command fails because no package manager exists in the image

#### Scenario: Stub command reads prompt file
- **WHEN** the container starts with a file at `/workspace/prompt.txt` containing "Hello world"
- **THEN** the container outputs "Hello world" to stdout and exits with code 0

#### Scenario: Missing prompt file
- **WHEN** the container starts without a file at `/workspace/prompt.txt`
- **THEN** the container exits with a non-zero exit code
