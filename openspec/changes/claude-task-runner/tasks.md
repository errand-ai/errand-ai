## 1. Image (do this first)

The image is the riskiest part and everything else depends on it. Build it before writing backend or frontend code.

- [ ] 1.1 Create `task-runner/Dockerfile.claude`: `BASE_IMAGE` build arg, `node:24` builder stage installing `@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}`, copy the installed package into the final image, and add a `claude` wrapper on PATH
- [ ] 1.2 Stage `bash` and its shared libraries from `debian:bookworm-slim`, following the base image's `git`/`curl`/`jq` staging pattern and its shared-library skip list
- [ ] 1.3 Set `DISABLE_AUTOUPDATER=1` in the image
- [ ] 1.4 Verify in a built container: `claude --version` succeeds, `bash -c 'echo $BASH_VERSION'` succeeds, `npm` and `pip` do not resolve, the process runs as UID 65532
- [ ] 1.5 Verify the Bash tool actually executes a command end-to-end (a stub Anthropic endpoint via `ANTHROPIC_BASE_URL` is sufficient and needs no credentials)
- [ ] 1.6 Confirm the per-architecture native binary resolves correctly for both `linux/amd64` and `linux/arm64`
- [ ] 1.7 Add the claude-task-runner image build job to `.github/workflows/build.yml`, matching the existing jobs' tagging and architectures
- [ ] 1.8 Capture stream-json fixtures from the pinned CLI version for the transformer tests

## 2. Data Model & Migration

- [ ] 2.1 Add `container_image` nullable Text column to `TaskProfile` in `errand/models.py`
- [ ] 2.2 Create the Alembic migration for the new column

## 3. Backend — Image Resolution & Runtime Allowlist

- [ ] 3.1 Add `CLAUDE_TASK_RUNNER_IMAGE` support and image resolution in `task_manager.py` (null → `TASK_RUNNER_IMAGE`, `"claude"` → claude image, other → verbatim), replacing the hard-coded `image=TASK_RUNNER_IMAGE` at container preparation
- [ ] 3.2 Add the runtime allowlist in `container_runtime.py`: `"claude"` permitted on `docker` and `apple`, rejected otherwise
- [ ] 3.3 Expose `claude_supported` from the status API based on `CONTAINER_RUNTIME`

## 4. Backend — Credential & Container Preparation

- [ ] 4.1 Register `claude_code_oauth_token` as a sensitive key in `errand/settings_registry.py`
- [ ] 4.2 Inject `CLAUDE_CODE_OAUTH_TOKEN` only when the resolved image is the claude image and the setting is non-empty
- [ ] 4.3 Record the token's save date for the renewal reminder
- [ ] 4.4 Confirm no other image variant — default or custom — receives the token

## 5. Backend — API

- [ ] 5.1 Accept and return `container_image` on the Task Profile CRUD endpoints
- [ ] 5.2 Reject `container_image: "claude"` at the API level when the runtime does not allow it
- [ ] 5.3 Restrict setting `container_image` to callers permitted to edit profiles

## 6. Task Runner — Delegation

- [ ] 6.1 Detect delegation preconditions: `claude` on PATH and `CLAUDE_CODE_OAUTH_TOKEN` set
- [ ] 6.2 Translate `/workspace/mcp.json` into a Claude-accepted config — inject `"type": "http"` where absent, write to a separate file, leave the canonical file untouched
- [ ] 6.3 Bridge `/workspace/skills/*` into `/workspace/.claude/skills/`
- [ ] 6.4 Build the `--disallowedTools` list from `EXCLUDED_CATALOG_TOOLS`, namespaced `mcp__errand__<tool>`
- [ ] 6.5 Implement the invocation via `subprocess.Popen` with `cwd=/workspace` and the flag set in the spec (including `--permission-mode bypassPermissions`, `--mcp-config`, `--strict-mcp-config`; not `--include-partial-messages`)
- [ ] 6.6 Implement the stream transformer: `system/init` → `agent_start`, `assistant` content blocks → `thinking` / `reasoning` / `tool_call`, `user` `tool_result` blocks → `tool_result` (attributed by `tool_use_id`, truncated to 500 chars), `result` → `agent_end`, everything else → `raw`
- [ ] 6.7 Verify MCP registration against the init event and emit an `error` event for any missing or failed server
- [ ] 6.8 Emit an `error` event for any `permission_denials` on the terminal `result` event
- [ ] 6.9 Determine success from the `result` event (`is_error`), never from the process exit status
- [ ] 6.10 Implement the fallback rule: fall back only when no `tool_call` was emitted; otherwise fail the task. Emit `claude_fallback` with `reason`, `terminal_reason`, and `fell_back` in both cases
- [ ] 6.11 Deliver the result through the existing path (`write_output_file`, `post_result_callback`), preferring a `submit_result` payload when the model called it

## 7. Frontend — Claude Token Card (this repo)

- [ ] 7.1 Add a `ClaudeTokenSettings.vue` card to the Security settings section alongside `McpApiKeySettings.vue`, with a password-style input, `claude setup-token` helper text, and Save/Clear
- [ ] 7.2 Display the ToS, quota, and reduced-safety-net disclaimer when a token is present
- [ ] 7.3 Show the recorded save date, the approximate one-year validity note, and a renewal reminder past eleven months — do not attempt to parse an expiry from the token

## 8. Frontend — Profile Editor (`@errand-ai/ui-components`)

The profile form lives in the shared component package, not in this repository.

- [ ] 8.1 Add the container image radio group (Default / Claude / Custom) with a text input for Custom to `TaskProfileListCard` in `@errand-ai/ui-components`
- [ ] 8.2 Hide the Claude option when `claude_supported` is false
- [ ] 8.3 Disable max turns, LLM timeout, and model with an explanatory note when Claude is selected
- [ ] 8.4 Show the container image in the profile summary card
- [ ] 8.5 Release the package and bump the dependency in `frontend/package.json`

## 9. Documentation

- [ ] 9.1 Create `task-runner/CUSTOM_IMAGES.md`: sample Dockerfile, base-image constraints (busybox and no bash, no runtime package managers, nonroot, entrypoint contract, output contract)
- [ ] 9.2 Document the delegation parity gap — no compaction, stall guard, tool-call recovery, file tools, per-command timeouts, or mid-task Google token refresh
- [ ] 9.3 Note in the operator docs that `MAX_TURNS`, `LLM_REQUEST_TIMEOUT`, and the LLM provider do not apply to delegated runs

## 10. Testing

- [ ] 10.1 Backend: `container_image` CRUD, image resolution for null / `"claude"` / custom, and the runtime allowlist including an unknown runtime
- [ ] 10.2 Backend: token injection for the claude image only — present, absent, default image, custom image
- [ ] 10.3 Task runner: MCP translation adds `"type": "http"`, preserves an existing type and headers, and leaves `/workspace/mcp.json` unmodified
- [ ] 10.4 Task runner: MCP verification emits an `error` event for a missing or failed server
- [ ] 10.5 Task runner: stream transformation for every mapped event type, driven by the captured fixtures, including `tool_result` attribution and truncation
- [ ] 10.6 Task runner: `agent_start` with `agent: "claude"` is emitted for a delegated run (the eval driver treats its absence as infra failure)
- [ ] 10.7 Task runner: exit status 0 with `is_error: true` is treated as failure
- [ ] 10.8 Task runner: fallback occurs when no tool call was emitted, and does NOT occur when one was — asserting the standard loop did not run in the second case
- [ ] 10.9 Task runner: an excluded MCP tool call is refused under the chosen permission mode (this is the guard on decision 7 in `design.md` — if it fails, the deny list must move server-side)
- [ ] 10.10 Task runner: `permission_denials` on the result event produce an `error` event
- [ ] 10.11 Task runner: result delivery reaches `write_output_file` and `post_result_callback`, and a `submit_result` payload takes precedence
- [ ] 10.12 Task runner: skills are bridged into `/workspace/.claude/skills/`
- [ ] 10.13 Frontend: Claude token card renders, masks, and shows the disclaimer
- [ ] 10.14 Image: build succeeds and the shell, CLI, and package-manager-absence assertions from 1.4 run in CI

## 11. Release

- [ ] 11.1 Bump `VERSION` per semver (minor — new backwards-compatible capability)
- [ ] 11.2 Verify the full stack locally with `docker compose -f testing/docker-compose.yml up --build`, running one task on the default image and one on the claude image
- [ ] 11.3 Confirm the CI build publishes all images and the Helm chart before merging
