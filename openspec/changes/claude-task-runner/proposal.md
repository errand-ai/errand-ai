## Why

Individual users running errand-desktop locally already pay for Claude Max subscriptions. Currently, all task execution uses API billing (OpenAI-compatible endpoints via LiteLLM), even for users who would prefer to leverage their existing subscription. By allowing the task-runner to delegate work to the `claude` CLI in headless mode (`claude -p`), users can run tasks against their Max subscription at no additional cost — the same way they'd manually run `claude -p` in a terminal.

## What Changes

- **New container image**: `claude-task-runner` image extending the base `task-runner` with Node.js and the Claude Code CLI (`@anthropic-ai/claude-code`)
- **Task Profile image selection**: Users can choose between default, claude, or custom container images per Task Profile
- **Claude delegation in task-runner**: When running in the claude-task-runner image, `main.py` tries `claude -p` first via `subprocess.Popen`, streaming events in real-time, falling back to the normal agent loop if claude fails
- **Event stream transformation**: Claude's `stream-json` output is transformed to errand's existing event format (tool_call, tool_result, thinking, agent_end) so the frontend renders progress without changes
- **Claude MCP config generation**: TaskManager generates `~/.claude/settings.json` inside the container alongside the existing `mcp.json`, giving claude CLI access to configured MCP servers (Playwright, Hindsight, etc.)
- **Claude OAuth credential storage**: Users provide a `claude setup-token` generated token via the Settings UI, stored as `CLAUDE_CODE_OAUTH_TOKEN` credential and injected into containers as an environment variable
- **K8s deployment lockout**: Claude image selection is disabled when `CONTAINER_RUNTIME=kubernetes` — this feature is restricted to local Docker/desktop deployments only
- **User-facing disclaimer**: Warning displayed when enabling claude integration about ToS implications, rate limits, and token expiry constraints

## Capabilities

### New Capabilities
- `claude-task-runner-image`: Dockerfile and build config for the claude-enabled task-runner container image (Node.js + Claude Code CLI)
- `claude-delegation`: Task-runner logic for delegating to `claude -p`, streaming event transformation, and fallback to normal agent loop
- `claude-credential-setup`: UI and backend for storing Claude OAuth tokens (`setup-token` flow) and injecting them into containers
- `claude-mcp-config`: Generation of Claude Code MCP settings (`~/.claude/settings.json`) from errand's MCP server configuration

### Modified Capabilities
- `task-profile-settings-ui`: Add container image selection (default / claude / custom) to Task Profile creation/editing UI
- `task-profile-worker-resolution`: Resolve container image from Task Profile when preparing containers
- `task-runner-image`: Support multiple image variants and custom user-specified images
- `container-runtime`: Validate claude image selection against deployment mode (reject on K8s)

## Impact

- **task-runner/**: New `main.py` execution path for claude delegation, new Dockerfile for claude variant
- **errand/task_manager.py**: Image resolution from Task Profile, Claude MCP config generation, credential injection
- **errand/container_runtime.py**: Image validation against deployment mode
- **errand/models.py**: `container_image` field on `TaskProfile`
- **frontend/**: Task Profile settings form (image selector), claude credential input, disclaimer UI
- **CI/CD**: Build and push claude-task-runner image alongside default image
- **Dependencies**: Node.js 20+ and `@anthropic-ai/claude-code` npm package in claude image
