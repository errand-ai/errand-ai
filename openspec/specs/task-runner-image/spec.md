## Purpose

Multi-stage Dockerfile for the task-runner container with Python, git, Node.js, gh CLI, and openspec tooling.

## Requirements

### Requirement: Task runner Dockerfile

The repository SHALL include a `task-runner/Dockerfile` that produces a minimal, hardened container image for executing tasks inside DinD. The Dockerfile SHALL use a multi-stage build with the following stages:

1. **python builder** (`python:3.11-slim`): Install Python dependencies via pip into a target directory. Additionally, install pip itself into a separate staging directory (`/pip-staging`) for use by the entrypoint script.
2. **git-builder** (`debian:bookworm-slim`): Install `git`, `openssh-client`, `ca-certificates`, `busybox`, `curl`, and `jq` system packages. Download the `gh` CLI binary from the GitHub releases tarball for the target architecture (`TARGETARCH`) and place it at `/usr/local/bin/gh`. Stage shared libraries needed by git, ssh, busybox, curl, and jq. Create the `.ssh` directory at `/home/nonroot/.ssh` with permissions 700.
3. **node-builder** (`node:22-bookworm-slim`): Run `npm install -g @fission-ai/openspec@latest` to install the openspec CLI globally. Stage npm itself into a separate directory (`/npm-staging`) for use by the entrypoint script. The node binary, global node_modules, openspec entry point, and staged npm SHALL be available for copying to the final stage.
4. **gws-builder** (`debian:bookworm-slim`): Download the Google Workspace CLI (`gws`) `*-unknown-linux-musl` release tarball from `github.com/googleworkspace/cli/releases` (matching `${GWS_VERSION}` and `TARGETARCH`) and clone the repository at the matching version tag to obtain the bundled agent skills (`skills/gws-*`). The musl-static target is required because the glibc target depends on `GLIBC_2.39`, which the distroless `python3-debian12` base does not provide. The `gws` binary and skill directories SHALL be available for copying to the final stage.
5. **final** (`gcr.io/distroless/python3-debian12:nonroot`): Copy Python packages from the python builder, staged pip to `/opt/pip-bootstrap/`, staged npm to `/opt/npm-bootstrap/`, staged binaries and libraries from git-builder (git, ssh, curl, jq, busybox, gh), node binary plus openspec from node-builder, and `gws` binary plus bundled skills from gws-builder. The skills SHALL be placed at `/opt/system-skills/gws/`. Copy `entrypoint.sh` to `/app/entrypoint.sh`. The working directory SHALL be `/workspace`. The entrypoint SHALL be `["/bin/sh", "/app/entrypoint.sh"]`.

The `gh` version, `openspec` version, and `gws` version SHALL be configurable via Docker build args with sensible defaults.

The following binaries SHALL be available in the final image: `git`, `ssh`, `ssh-keygen`, `ssh-keyscan`, `curl`, `jq`, `gh`, `node`, `openspec`, `gws`, and busybox applets (`sh`, `cat`, `ls`, `grep`, etc.).

#### Scenario: Image builds successfully

- **WHEN** `docker build -t task-runner task-runner/` is run
- **THEN** the image builds without errors and is tagged `task-runner`

#### Scenario: Image runs as non-root

- **WHEN** the task runner container starts
- **THEN** the process runs as the `nonroot` user (UID 65532)

#### Scenario: Python application executes

- **WHEN** the container starts with required environment variables and input files
- **THEN** the entrypoint script runs and ultimately starts the Python application which produces structured output to stdout

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

#### Scenario: Staged pip is available for entrypoint

- **WHEN** the container starts
- **THEN** `/opt/pip-bootstrap/` contains pip modules usable via `PYTHONPATH=/opt/pip-bootstrap python3 -m pip`

#### Scenario: Staged npm is available for entrypoint

- **WHEN** the container starts
- **THEN** `/opt/npm-bootstrap/` contains npm usable via explicit path invocation

#### Scenario: pip is not on PATH

- **WHEN** the container starts
- **THEN** running `which pip` returns no result

#### Scenario: gws CLI is available

- **WHEN** the container starts
- **THEN** `gws --version` executes successfully and outputs a Google Workspace CLI version string

#### Scenario: gws skills are bundled

- **WHEN** the container starts
- **THEN** `/opt/system-skills/gws/` contains SKILL.md files for Google Workspace services (sourced from the upstream `googleworkspace/cli` repository)
