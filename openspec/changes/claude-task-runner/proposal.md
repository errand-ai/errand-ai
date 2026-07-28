## Why

Individual users running errand's macOS desktop app already pay for Claude Max subscriptions. Today every task is billed per token through an OpenAI-compatible endpoint, even for users who would rather spend subscription capacity they have already bought. Letting the task-runner delegate to the `claude` CLI in headless mode (`claude -p`) runs tasks against that subscription at no incremental cost — the same thing the user could do by hand in a terminal.

This proposal was first written in March 2026 and has been revised after a build spike against the current codebase (see `design.md` → *Spike evidence*). The premise held; most of the original mechanics did not.

## What Changes

- **New container image**: a `claude-task-runner` image extending the base `task-runner` with the Claude Code CLI. The base is distroless with busybox only, and Claude Code refuses to run its Bash tool without a shell it recognises, so the image also stages a real `bash` (~2 MB) alongside the CLI.
- **Task Profile image selection**: a `container_image` field on `TaskProfile` selecting default, claude, or a custom image.
- **Claude delegation in task-runner**: when the CLI and a token are present, `main.py` runs the task via `claude -p`, transforming its `stream-json` output into errand's existing event protocol. Delegation is attempted **once**, and fallback to the Python agent loop is deliberately narrow — a failure that happens after Claude's first tool call is a task failure, not a retry, because the task may already have sent mail or posted messages.
- **Event stream transformation**: Claude's real event shapes (`system`, `assistant`, `user`, `result`) are mapped onto errand's `agent_start` / `tool_call` / `tool_result` / `thinking` / `agent_end` events, plus a new `raw` type for anything unrecognised.
- **Claude MCP config**: the runner passes errand's existing `/workspace/mcp.json` to `--mcp-config`, injecting the `"type": "http"` discriminator Claude Code requires, and verifies every configured server actually registered — without the discriminator, servers are dropped silently.
- **Tool exclusion carried across**: the seven eval/admin MCP tools kept out of the default agent's catalog are denied explicitly on the claude path, which would otherwise see every tool the shared MCP key exposes.
- **Skill bridging**: errand skills installed at `/workspace/skills/` are exposed to Claude Code at `/workspace/.claude/skills/`.
- **Claude OAuth credential**: a `claude setup-token` value stored as a sensitive setting and injected as `CLAUDE_CODE_OAUTH_TOKEN` only into claude images.
- **Runtime allowlist**: claude image selection is permitted on the `docker` and `apple` runtimes and rejected on `kubernetes`.
- **User-facing disclaimer**: ToS, quota-sharing, and reduced-safety-net warnings shown when the token is saved.

## Capabilities

### New Capabilities
- `claude-task-runner-image`: Dockerfile, bash staging, per-architecture native binary handling, version pinning, and CI build for the claude-enabled image
- `claude-delegation`: invocation, permission mode, stream transformation, result extraction, fallback conditions, and disclosure of the runner safety nets that do not apply
- `claude-credential-setup`: storage, masking, injection, and disclaimer for the Claude OAuth token
- `claude-mcp-config`: translation of `/workspace/mcp.json` into a Claude-accepted MCP config, plus registration verification

### Modified Capabilities
- `structured-task-events`: add `raw` and `claude_fallback` event types to the documented protocol
- `task-profile-settings-ui`: add container image selection to the profile editor (delivered via `@errand-ai/ui-components`)
- `task-profile-worker-resolution`: resolve the container image from the profile
- `container-runtime`: validate claude image selection against the active runtime
- `task-runner-image`: document the base-image contract for custom images

## Impact

- **task-runner/**: new delegation module and stream transformer alongside `main.py`; new `Dockerfile.claude`
- **errand/task_manager.py**: image resolution, token injection, skill bridging for claude images
- **errand/container_runtime.py**: runtime allowlist for the claude image
- **errand/models.py** + Alembic: `container_image` column on `task_profiles`
- **errand/settings_registry.py**: new sensitive `claude_code_oauth_token` key
- **frontend/**: Claude token card in the local Security settings section; the profile editor field ships in `@errand-ai/ui-components` and lands here as a dependency bump
- **CI/CD**: a fifth multi-arch image build job
- **Dependencies**: `@anthropic-ai/claude-code` (per-architecture native binary, ~270 MB) and `bash` in the claude image only
