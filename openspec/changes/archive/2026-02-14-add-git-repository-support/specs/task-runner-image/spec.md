## MODIFIED Requirements

### Requirement: Task runner Dockerfile

The repository SHALL include a `task-runner/Dockerfile` that produces a minimal, hardened container image for executing tasks inside DinD. The Dockerfile SHALL use a multi-stage build: the first stage uses a Python slim image to install dependencies via pip into a target directory, and the second stage uses the same Python slim image to install `git` and `openssh-client` system packages and copy the installed binaries and libraries. The final stage uses `gcr.io/distroless/python3-debian12:nonroot` as the base. The installed Python packages, the application source (`main.py`), the git binary with its required shared libraries, and the openssh-client binaries (`ssh`, `ssh-keygen`) with their required shared libraries SHALL be copied into the final image. The `~/.ssh` directory SHALL be created at `/home/nonroot/.ssh` with permissions 700 owned by the nonroot user (UID 65532). The working directory SHALL be `/workspace`. The entrypoint SHALL be `["python3", "/app/main.py"]`.

#### Scenario: Image builds successfully

- **WHEN** `docker build -t task-runner task-runner/` is run
- **THEN** the image builds without errors and is tagged `task-runner`

#### Scenario: Image runs as non-root

- **WHEN** the task runner container starts
- **THEN** the process runs as the `nonroot` user (UID 65532)

#### Scenario: Python application executes

- **WHEN** the container starts with required environment variables and input files
- **THEN** the Python application runs and produces structured output to stdout

#### Scenario: Dependencies are available

- **WHEN** the container starts
- **THEN** the `openai-agents`, `mcp`, and `pydantic` Python packages are importable

#### Scenario: Git is available

- **WHEN** the container starts
- **THEN** `git --version` executes successfully and outputs a git version string

#### Scenario: SSH client is available

- **WHEN** the container starts
- **THEN** `ssh -V` executes successfully and outputs an OpenSSH version string

#### Scenario: SSH directory exists with correct permissions

- **WHEN** the container starts
- **THEN** `/home/nonroot/.ssh` exists with permissions 700 owned by UID 65532
