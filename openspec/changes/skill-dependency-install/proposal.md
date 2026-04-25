## Why

AI skills often require Python or Node packages that are not included in the task-runner base image (e.g., `google-genai` and `pillow` for image generation). Today, the task-runner uses a distroless base image with no package managers available at runtime, so skills that declare `pip install` prerequisites simply cannot work. Adding every possible dependency to the base image is impractical and undermines the minimal/secure image philosophy. We need a mechanism for skills to declare their dependencies and have them installed automatically at task startup, without giving the agent runtime access to package managers.

## What Changes

- Skills can declare Python dependencies via a `requirements.txt` file in their skill directory, and Node dependencies via a `package.json` file
- The task-runner Dockerfile is modified to include pip and npm in isolated staging paths (not on PATH, not in default PYTHONPATH)
- The task-runner entrypoint changes from a direct `python3` invocation to a shell wrapper that: scans skill directories for dependency files, installs them, deletes all package manager binaries, then exec's into the agent
- The agent never has access to pip, npm, or ensurepip — they are removed before the agent process starts

## Capabilities

### New Capabilities
- `skill-dependency-install`: Automated installation of skill-declared Python and Node dependencies at task-runner startup, with package managers removed before agent execution

### Modified Capabilities
- `task-runner-image`: Dockerfile changes to stage pip/npm in isolated paths and use a shell entrypoint wrapper
- `agent-skill-loading`: Skills documentation updated to describe the `requirements.txt` and `package.json` convention

## Impact

- **task-runner/Dockerfile**: New builder stages to stage pip and npm; entrypoint changes from `["python3", "/app/main.py"]` to a shell wrapper script
- **task-runner/entrypoint.sh**: New file — scans skills for deps, installs, removes installers, exec's agent
- **Security model**: Package managers exist only during the init phase (before agent has control) and are deleted before `exec`. Agent's `execute_command` cannot access pip/npm
- **Startup time**: Tasks using skills with dependencies will have additional startup time (10-30s for pip install). Tasks without skill dependencies are unaffected (fast no-op check). Task profiles already support selective skill inclusion to control this
- **Image size**: Small increase from staging pip/npm binaries (~15MB). No change to runtime footprint for tasks without dependencies
