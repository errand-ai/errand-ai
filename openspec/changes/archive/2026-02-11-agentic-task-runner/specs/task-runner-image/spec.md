## MODIFIED Requirements

### Requirement: Task runner Dockerfile
The repository SHALL include a `task-runner/Dockerfile` that produces a minimal, hardened container image for executing tasks inside DinD. The Dockerfile SHALL use a multi-stage build: the first stage uses a Python slim image to install dependencies via pip into a target directory, and the final stage uses `gcr.io/distroless/python3-debian12:nonroot` as the base. The installed Python packages and the application source (`main.py`) SHALL be copied into the final image. The working directory SHALL be `/workspace`. The entrypoint SHALL be `["python3", "/app/main.py"]`.

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
