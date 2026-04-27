## MODIFIED Requirements

### Requirement: Task runner Dockerfile
The repository SHALL include a `task-runner/Dockerfile` that produces a minimal, hardened container image for executing tasks inside DinD. The Dockerfile SHALL use a multi-stage build with the following stages:

1. **python builder** (`python:3.11-slim`): Install Python dependencies via pip into a target directory.
2. **git-builder** (`debian:bookworm-slim`): Install `git`, `openssh-client`, `ca-certificates`, `busybox`, and `curl` system packages. Download the `gh` CLI binary from the GitHub releases tarball for the target architecture (`TARGETARCH`) and place it at `/usr/local/bin/gh`. Stage shared libraries needed by git, ssh, busybox, and curl. Create the `.ssh` directory at `/home/nonroot/.ssh` with permissions 700.
3. **node-builder** (`node:22-bookworm-slim`): Run `npm install -g @fission-ai/openspec@latest` to install the openspec CLI globally. The node binary, global node_modules, and openspec entry point SHALL be available for copying to the final stage.
4. **gws-builder** (`debian:bookworm-slim`): Download the Google Workspace CLI (`gws`) `*-unknown-linux-musl` release tarball from `github.com/googleworkspace/cli/releases` (matching `${GWS_VERSION}` and `TARGETARCH`) and clone the repository at the matching version tag to obtain the bundled agent skills (`skills/gws-*`). The musl-static target is required because the glibc target depends on `GLIBC_2.39`, which the distroless `python3-debian12` base does not provide. The `gws` binary and skill directories SHALL be available for copying to the final stage.
5. **final** (`gcr.io/distroless/python3-debian12:nonroot`): Copy Python packages from the python builder, staged binaries and libraries from git-builder (git, ssh, curl, busybox, gh), node binary plus openspec from node-builder, and `gws` binary plus bundled skills from gws-builder. The skills SHALL be placed at `/opt/system-skills/gws/`. The working directory SHALL be `/workspace`. The entrypoint SHALL be `["python3", "/app/main.py"]`.

The `gh` version, `openspec` version, and `gws` version SHALL be configurable via Docker build args with sensible defaults.

The following binaries SHALL be available in the final image: `git`, `ssh`, `ssh-keygen`, `ssh-keyscan`, `curl`, `gh`, `node`, `openspec`, `gws`, and busybox applets (`sh`, `cat`, `ls`, `grep`, etc.).

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

#### Scenario: gh CLI is available
- **WHEN** the container starts
- **THEN** `gh --version` executes successfully and outputs a GitHub CLI version string

#### Scenario: Node.js is available
- **WHEN** the container starts
- **THEN** `node --version` executes successfully and outputs a Node.js version string (v22.x)

#### Scenario: openspec CLI is available
- **WHEN** the container starts
- **THEN** `openspec --version` executes successfully and outputs an openspec version string

#### Scenario: gws CLI is available
- **WHEN** the container starts
- **THEN** `gws --version` executes successfully and outputs a Google Workspace CLI version string

#### Scenario: gws skills are bundled
- **WHEN** the container starts
- **THEN** `/opt/system-skills/gws/` contains SKILL.md files for Google Workspace services (sourced from the upstream `googleworkspace/cli` repository)
