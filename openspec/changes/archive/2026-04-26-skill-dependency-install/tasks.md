## 1. Entrypoint Script

- [x] 1.1 Create `task-runner/entrypoint.sh` — shell script that scans `/workspace/skills/*/requirements.txt` and `/workspace/skills/*/package.json`, installs dependencies via pip/npm from staged bootstrap paths, removes all package manager files (pip, npm, ensurepip), then exec's into `python3 /app/main.py`
- [x] 1.2 Ensure entrypoint is a fast no-op when no dependency files exist (skip straight to exec)

## 2. Dockerfile Changes

- [x] 2.1 In the python builder stage, add a step to install pip itself into `/pip-staging` (separate from the application dependencies)
- [x] 2.2 In the node-builder stage, stage npm and its dependencies into `/npm-staging`
- [x] 2.3 In the final stage, copy staged pip to `/opt/pip-bootstrap/` and staged npm to `/opt/npm-bootstrap/`
- [x] 2.4 Copy `entrypoint.sh` to `/app/entrypoint.sh` in the final stage
- [x] 2.5 Change the ENTRYPOINT from `["python3", "/app/main.py"]` to `["/bin/sh", "/app/entrypoint.sh"]`

## 3. Testing

- [x] 3.1 Build the task-runner image locally and verify it starts correctly with no skills (no-op entrypoint path)
- [x] 3.2 Test with a skill that has a `requirements.txt` (e.g., nano-banana with `google-genai` and `pillow`) — verify packages are importable after startup
- [x] 3.3 Verify that `pip`, `python3 -m pip`, `python3 -m ensurepip`, and `npm` are all unavailable after the agent starts
- [x] 3.4 Run the existing errand test suite to verify no regressions

## 4. Spec Updates

- [x] 4.1 Update `openspec/specs/task-runner-image/spec.md` by archiving the delta spec from this change
