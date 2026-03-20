## 1. Data Model & Migration

- [ ] 1.1 Add `container_image` nullable Text column to `TaskProfile` model in `errand/models.py`
- [ ] 1.2 Create Alembic migration for the new `container_image` column

## 2. Backend — Image Resolution & Validation

- [ ] 2.1 Add `CLAUDE_TASK_RUNNER_IMAGE` env var support and image resolution logic in `task_manager.py` (null → default, "claude" → claude image, other → custom)
- [ ] 2.2 Add K8s validation in container runtime — reject `"claude"` image when `CONTAINER_RUNTIME=kubernetes`
- [ ] 2.3 Expose `claude_supported` flag via settings/status API endpoint based on `CONTAINER_RUNTIME` value

## 3. Backend — Credential Injection & MCP Config

- [ ] 3.1 Inject `CLAUDE_CODE_OAUTH_TOKEN` env var into claude-task-runner containers when credential exists
- [ ] 3.2 Generate `~/.claude/settings.json` (Claude MCP config) from resolved MCP servers and inject into claude-task-runner containers
- [ ] 3.3 Ensure `CLAUDE_CODE_OAUTH_TOKEN` is NOT injected for default task-runner containers

## 4. Backend — API Updates

- [ ] 4.1 Update Task Profile CRUD API endpoints to accept and return `container_image` field
- [ ] 4.2 Add validation: reject `container_image: "claude"` on K8s deployments at API level

## 5. Task Runner — Claude Delegation

- [ ] 5.1 Add claude detection logic in `task-runner/main.py` (check `which claude` + `CLAUDE_CODE_OAUTH_TOKEN` presence)
- [ ] 5.2 Implement `run_with_claude()` function — `subprocess.Popen` invoking `claude -p` with `--output-format stream-json --verbose --allowedTools`
- [ ] 5.3 Implement stream event transformer — map claude stream-json events to errand event format (tool_call, tool_result, thinking, agent_end, raw)
- [ ] 5.4 Implement result extraction — parse final `result` event from stream, format as TaskRunnerOutput JSON on stdout
- [ ] 5.5 Implement try/fallback — on claude failure (non-zero exit, no result event), emit `claude_fallback` event and execute standard agent loop

## 6. Claude Task Runner Image

- [ ] 6.1 Create `task-runner/Dockerfile.claude` extending base image with Node.js 22 and `@anthropic-ai/claude-code` (version-pinned via build arg)
- [ ] 6.2 Verify claude CLI is available on PATH and runs as nonroot user in the image
- [ ] 6.3 Add claude-task-runner image build to CI pipeline (`.github/workflows/build.yml`)

## 7. Frontend — Task Profile UI

- [ ] 7.1 Add container image radio group (Default / Claude / Custom) to Task Profile create/edit form
- [ ] 7.2 Conditionally hide Claude option when `claude_supported` is false (K8s deployments)
- [ ] 7.3 Show custom image text input when "Custom" is selected
- [ ] 7.4 Display container image in profile summary cards

## 8. Frontend — Credential UI & Disclaimer

- [ ] 8.1 Add "Claude Code Token" field to Credentials settings section with helper text about `claude setup-token`
- [ ] 8.2 Display ToS/usage disclaimer warning banner when token is entered
- [ ] 8.3 Show token expiry date and renewal warning (within 30 days)

## 9. Documentation

- [ ] 9.1 Create `task-runner/CUSTOM_IMAGES.md` with instructions for extending the base task-runner image (sample Dockerfile, compatibility guidelines)

## 10. Testing

- [ ] 10.1 Backend tests: TaskProfile `container_image` field CRUD, image resolution logic, K8s validation
- [ ] 10.2 Backend tests: Claude credential injection (present/absent/default-image scenarios)
- [ ] 10.3 Backend tests: Claude MCP config generation from MCP server list
- [ ] 10.4 Task runner tests: stream event transformation (each event type mapping)
- [ ] 10.5 Task runner tests: claude fallback on failure (auth error, rate limit, missing binary)
- [ ] 10.6 Frontend tests: profile form with image selection, conditional Claude option visibility
- [ ] 10.7 Docker build test: `docker build -f task-runner/Dockerfile.claude` succeeds and claude CLI is available
