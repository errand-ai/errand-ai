## Context

The task-runner container uses `gcr.io/distroless/python3-debian12:nonroot` as its base — a minimal image with no package managers. Skills are injected as tar archives into `/workspace/skills/` before the agent starts. Currently, skills that require additional Python or Node packages (e.g., `google-genai`, `pillow`) cannot function because the agent has no way to install them. We need dependency installation without giving the agent runtime access to package managers.

The task-runner entrypoint is currently `["python3", "/app/main.py"]`. Skills are available at `/workspace/skills/` by the time the entrypoint runs — on K8s they're extracted by the init container, on Docker they're injected via `put_archive` before container start.

## Goals / Non-Goals

**Goals:**
- Skills can declare Python dependencies (`requirements.txt`) and Node dependencies (`package.json`) that are automatically installed at task startup
- Package managers (pip, npm) are completely removed from the container before the agent process starts
- Zero overhead for tasks that don't use skills with dependencies
- Works consistently across all container runtimes (Docker, Kubernetes, Apple)

**Non-Goals:**
- Dependency caching across tasks (follow-up work)
- Package allowlisting (trust boundary is the skill declaration, not individual packages)
- System-level package installation (apt/apk) — skills must work with manylinux wheels or pre-built Node packages
- Automatic dependency resolution for DB-sourced skills beyond what they declare in their files array

## Decisions

### D1: Shell entrypoint wrapper instead of init container

**Decision**: Use a shell script (`entrypoint.sh`) as the container entrypoint that handles dependency installation, then `exec`s into the Python agent.

**Alternatives considered**:
- *K8s init container with full Python image*: Only works on K8s; Docker and Apple runtimes would need a separate mechanism. The entrypoint approach is runtime-agnostic.
- *Server-side dependency bundling*: Task manager pre-installs packages and injects them as a tar. Fails for packages with native extensions when server and runner architectures differ (e.g., ARM Mac server, AMD64 Linux runner).

**Rationale**: The entrypoint runs inside the target container on the target architecture, so native wheels are always correct. It works identically across all three runtimes because it doesn't depend on external orchestration.

### D2: Stage pip and npm in isolated paths

**Decision**: Copy pip and npm into `/opt/pip-bootstrap/` and `/opt/npm-bootstrap/` respectively during the Docker build. These paths are not on `PATH` and not in `PYTHONPATH`. The entrypoint script invokes them via explicit paths, then deletes them entirely.

**Rationale**: The agent's `execute_command` runs shell commands after `main.py` starts. By that point, `rm -rf` has removed all package manager binaries and modules. Even if the agent tries `pip`, `python3 -m pip`, `python3 -m ensurepip`, or searches the filesystem, nothing is found.

### D3: Dependency declaration via convention files

**Decision**: Skills declare dependencies using standard ecosystem files:
- Python: `requirements.txt` in the skill root directory
- Node: `package.json` in the skill root directory

**Alternatives considered**:
- *SKILL.md frontmatter*: Would require parsing YAML frontmatter in a shell script, adding complexity. Standard files are universally understood and can be tested independently.

**Rationale**: `requirements.txt` and `package.json` are the native formats developers already know. Git-sourced skills include them as files. DB-sourced skills include them via the existing `files` array in `upsert_skill`. The entrypoint just walks `/workspace/skills/*/` looking for these files — it doesn't need to know the skill source.

### D4: Install targets and environment variables

**Decision**: 
- Python packages install to `/opt/skill-deps/python/` via `pip install --target`
- Node packages install to `/opt/skill-deps/node/node_modules/` via `npm install --prefix`
- Entrypoint prepends `/opt/skill-deps/python/` to `PYTHONPATH` and sets `NODE_PATH=/opt/skill-deps/node/node_modules`

**Rationale**: Installing to a dedicated directory rather than the existing site-packages avoids mutating or overwriting the base image's pre-installed packages (openai-agents, mcp, pydantic, httpx). Because `/opt/skill-deps/python/` is prepended to `PYTHONPATH`, skill-installed packages take precedence at import time if they conflict with a base package.

### D5: Entrypoint is a no-op when no dependencies exist

**Decision**: The entrypoint script checks for the existence of `requirements.txt` or `package.json` files before attempting any installation. If no skills have dependencies, the script immediately `exec`s into the agent with no additional overhead.

**Rationale**: Most tasks won't use skills with heavyweight dependencies. The common path should be fast.

## Risks / Trade-offs

**[Risk] Native extension packages may fail on distroless** → Most popular packages (Pillow, numpy, etc.) ship manylinux wheels that bundle their own native libraries. Packages requiring system-level libraries not present in distroless will fail at import time. This is a documentation concern — skill authors should test their skills in the task-runner image. Mitigation: document the limitation clearly.

**[Risk] Conflicting dependencies between skills** → Two skills could declare conflicting versions of the same package. `pip install` will resolve to one version. Mitigation: this is the same problem any Python project faces and is acceptable for v1. Task profiles can isolate conflicting skills to different profiles.

**[Risk] Network access required at startup** → `pip install` and `npm install` require network access to download packages. If the container has restricted egress, installation will fail. Mitigation: document the requirement. The task-runner already requires network access for LLM API calls and MCP servers.

**[Risk] Startup time increase** → Installation adds 10-30 seconds for Python, potentially more for Node. Mitigation: task profiles already support selective skill inclusion. Fast tasks exclude heavyweight skills.
