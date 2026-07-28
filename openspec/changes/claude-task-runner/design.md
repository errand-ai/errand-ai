## Context

Errand's task-runner executes tasks in containers using an OpenAI-compatible agent loop billed per token. Individual users running the macOS desktop app (the `apple` container runtime) often already hold Claude Max subscriptions. The Claude Code CLI supports headless execution (`claude -p`) authenticated by a `CLAUDE_CODE_OAUTH_TOKEN`, so those tasks can run against the subscription instead.

The runner streams structured JSON events on stderr (`agent_start`, `thinking`, `reasoning`, `tool_call`, `tool_result`, `agent_end`, `error` — see `openspec/specs/structured-task-events/`), which the container runtime forwards to Valkey and on to the frontend. Any delegation path must preserve that pipeline.

Running the official CLI binary in a container is analogous to Anthropic's own Claude Code GitHub Action, which uses the same token mechanism. That is not the same thing as the third-party OAuth extraction Anthropic shut down in January 2026, which replaced the client entirely.

Since this change was first drafted the codebase has moved considerably (v0.70 → v0.140). The task-runner base is now distroless with busybox and no package managers; the Vue components for settings have moved to `@errand-ai/ui-components`; and the runner has grown compaction, a stall guard, tool-call recovery, a lazy tool catalog, mid-task Google token refresh, and a `submit_result`/callback result contract. Those changes are what most of the decisions below are reacting to.

## Spike evidence

A build spike ran the real CLI (v2.1.220) inside the real base image, driven against a stub Anthropic endpoint so no credentials were involved. Findings that drove the decisions:

1. **The Bash tool cannot run on busybox.** Every Bash call returned `Error: No suitable shell found. Claude CLI requires a Posix shell environment.` Setting `SHELL` to `/bin/sh`, `/bin/ash`, or `/usr/bin/busybox` changed nothing. Staging Debian's `bash` (5.2.15, ~2 MB) fixed it: the same probe then returned `SPIKE_BASH_RAN`, `/usr/bin/bash`, `is_error: false`. Everything *else* worked without bash, so an image missing it would fail only at the first Bash call.
2. **Exit codes do not signal failure.** An unauthenticated run exited **0** with `{"is_error": true, "terminal_reason": "api_error", "result": "Not logged in · Please run /login"}`. Any fallback keyed on a non-zero exit status would never fire.
3. **The npm package is a wrapper around a per-architecture native binary** (`bin/claude.exe`, 271 MB, resolved via `@anthropic-ai/claude-code-linux-<arch>`). Image size went 580 MB → 938 MB, not the ~90 MB originally assumed.
4. **Real stream events are `system` (init / api_retry), `assistant`, `user`, `result`.** There are no bare `content_block_start` or `text_delta` events; those exist only nested inside `stream_event` and only with `--include-partial-messages`. Tool calls arrive as `tool_use` content blocks on `assistant`; results as `tool_result` blocks on `user`, with a sibling `tool_use_result` object carrying `stdout`/`stderr`.
5. **MCP servers without `"type"` are dropped silently.** `{"url": ...}` yielded `mcp_servers: []` and no error; `{"type": "http", "url": ...}` yielded `[{"name": "errand", "status": "failed"}]` (failed only because the spike pointed at a dead port).
6. **Denied tools fail quietly.** Without an allowlist the Bash call was rejected (`non_execution_kind: "user-rejected"`) yet the run finished `terminal_reason: "completed"`, exit 0 — a task that did nothing and looked successful. The only signal is the `permission_denials` array on the `result` event.
7. `claude doctor` reports `Auto-updates: enabled` by default, and `/home/nonroot` is writable so `~/.claude` is created without extra work.

Not covered by the spike: a real subscription token end-to-end, rate-limit behaviour, and whether `--bare` (documented as the future default for `-p`, and which never reads OAuth) breaks the token path.

## Goals / Non-Goals

**Goals:**
- Run tasks against a user's Claude Max subscription via `claude -p` on desktop/local deployments
- Preserve the live streaming UX with no frontend rendering changes beyond two new event types
- Keep the tool-exposure boundary the default agent has, rather than widening it
- Make the delegation path's reduced safety nets explicit rather than implied

**Non-Goals:**
- Kubernetes/Helm production deployments
- OAuth token refresh (rely on `claude setup-token`)
- Replacing the Python agent loop — this is an alternative path, not a successor
- Reimplementing the runner's compaction, stall guard, or tool-call recovery inside the claude path (Claude Code has its own equivalents; parity is documented, not built)
- Keychain extraction from the desktop app

## Decisions

### 1. Authentication via `claude setup-token`

**Decision**: Users run `claude setup-token` and paste the value into Settings. It is stored as a sensitive `claude_code_oauth_token` setting and injected as `CLAUDE_CODE_OAUTH_TOKEN` into claude images only.

**Alternatives**: Keychain extraction (couples to the desktop app, fragile); a custom OAuth refresh flow (reverse-engineering Anthropic's endpoints risks bans); an API key (defeats the purpose — that is API billing).

**Rationale**: Same mechanism as Anthropic's GitHub Action, no refresh machinery, works on any runtime that can run the CLI. The `settings_registry` already supports sensitive keys with masking, so no new storage concept is needed.

**Revised from the original**: the original spec required parsing and displaying the token's expiry. `sk-ant-oat01-…` is an opaque token, not a JWT — there is nothing to parse. The UI states the documented ~1-year validity and records the date the token was saved instead.

### 2. Single attempt, narrow fallback

**Decision**: Delegation is attempted once. The runner falls back to the Python agent loop **only** when Claude fails before its first tool call — that is: the binary is missing, the token is absent, or the `result` event reports failure with an empty `permission_denials` array and no `tool_use` block was seen. Any failure after the first tool call fails the task and emits `claude_fallback` with `fell_back: false`.

**Alternatives**: unconditional fallback (the original design); no fallback at all.

**Rationale**: Unconditional fallback re-runs a task that may already have sent an email, posted to Slack, or pushed a commit. Errand tasks routinely have external side effects, and rate-limit failures in particular tend to happen mid-run. Pre-first-tool-call failures are the ones that are provably side-effect-free, and they cover the cases users will actually hit on day one (bad token, expired token, missing binary).

**Consequence**: the fallback condition must be evaluated from the `result` event, not the process exit code, which is 0 even for auth failure (spike finding 2).

### 3. Separate image, with bash staged

**Decision**: `task-runner/Dockerfile.claude` extends the base image, copies the CLI from a `node:24` builder stage, and stages `bash` plus its shared libraries from `debian:bookworm-slim` using the same pattern the base uses for `git`, `curl`, and `jq`. `DISABLE_AUTOUPDATER=1` is set in the image.

**Alternatives**: runtime `npm install` (impossible — the entrypoint deletes pip and npm before the agent starts, by design); baking claude into the base image (every user pays ~360 MB); mounting the host's installation (platform-dependent).

**Rationale**: Opt-in cost. Adding bash is a deliberate, scoped weakening of the base image's minimalism, confined to the claude variant — the default runner keeps busybox only. Auto-update must be off: the image intentionally has no package managers, and an in-place update would defeat the pinned version.

**Note on architecture**: the npm package resolves a native binary per platform, so the builder stage must run for the target architecture. CI's existing QEMU/buildx setup handles this, but a single `node_modules` cannot be copied across architectures.

### 4. Stream transformation from real event shapes

**Decision**: Run `--output-format stream-json --verbose`, read stdout line by line, and emit errand events on stderr:

```
claude -p --output-format stream-json --verbose (stdout)
  → transformer reads NDJSON
  → emits errand events to stderr
  → runtime async_run() → Valkey → frontend
```

| Claude event | Errand event |
|---|---|
| `system` / `init` | `agent_start` (`agent: "claude"`), plus MCP verification (decision 6) |
| `assistant` message, `text` block | `thinking` |
| `assistant` message, `thinking` block | `reasoning` |
| `assistant` message, `tool_use` block | `tool_call` (`tool`, `args`) |
| `user` message, `tool_result` block | `tool_result` (`tool`, `output`, `length`; truncated to 500 chars) |
| `result` | `agent_end` |
| `system` / `api_retry`, anything unrecognised | `raw` |

`--include-partial-messages` is **not** used: token-level deltas would multiply event volume for no gain, since the existing UI renders whole `thinking` blocks.

**Rationale**: These are the shapes the CLI actually emits (spike finding 4). `agent_start` matters beyond cosmetics — the eval driver classifies a transcript without it as an infra failure, so a claude-run eval would otherwise be silently excluded from model scores.

### 5. Task Profile `container_image` field

**Decision**: A nullable `container_image` text column on `TaskProfile`: `null` → `TASK_RUNNER_IMAGE`, `"claude"` → `CLAUDE_TASK_RUNNER_IMAGE` (default `claude-task-runner:latest`), any other string → used verbatim.

**Rationale**: Clean extension of the existing profile system, resolved at container preparation time.

**Trust boundary**: a custom image receives the same injected material as the default one — SSH key, GitHub token, MCP bearer, per-task env. Choosing a profile image is therefore an administrator-level action, and the field is editable only by users who can already edit profiles.

### 6. MCP via `--mcp-config`, with type injection and verification

**Decision**: The runner passes `/workspace/mcp.json` to `--mcp-config` together with `--strict-mcp-config`, injecting `"type": "http"` into each server entry that lacks it. After `system/init` arrives, it compares the reported `mcp_servers` against the configured set and emits an `error` event naming any server that failed to register or is missing.

**Alternatives**: generating `~/.claude/settings.json` (the original design — factually wrong; `settings.json` does not carry `mcpServers`); server-side translation in `task_manager` (would fork the canonical `mcp.json` for one image variant).

**Rationale**: errand's `mcp.json` is already `{"mcpServers": {name: {url, headers}}}`, one field short of what Claude Code accepts. Doing the injection in the runner keeps `mcp.json` canonical for the default path. Verification is not optional: a missing `type` produces an empty server list and no error at all (spike finding 5), which would present as a task that mysteriously ignored its tools.

### 7. Permissions and tool exclusion

**Decision**: Invoke with `--permission-mode bypassPermissions` and an explicit `--disallowedTools` list built from `EXCLUDED_CATALOG_TOOLS`, namespaced as `mcp__errand__<tool>`. Any `permission_denials` on the `result` event are emitted as an `error` event.

**Alternatives**: `--allowedTools` enumeration (brittle — the shell-expansion rules deny commands that look allowed, and the failure is silent); `dontAsk` or `acceptEdits` (both leave non-file commands needing per-rule approval).

**Rationale**: The container *is* the sandbox — the default agent already has unrestricted `execute_command` inside it — so prompting has no meaning here and the permission system's only useful role is the deny list. The exclusion matters: `EXCLUDED_CATALOG_TOOLS` (`clone_task_profile`, `delete_task_profile`, `search_tasks`, and the four eval-run tools) is enforced today **only** in the task-runner's catalog builder, not server-side. Claude reaching the errand MCP server with the shared `mcp_api_key` would otherwise see all of them.

**Open risk**: if `bypassPermissions` is found to override deny rules, the deny list must move server-side. A task-runner test asserts an excluded tool is actually refused, so this fails loudly rather than silently.

### 8. Skills bridged into `.claude/skills`

**Decision**: For claude images, the runner copies `/workspace/skills/<name>/` into `/workspace/.claude/skills/<name>/` before invoking the CLI. Claude Code discovers project skills from `.claude/skills` relative to its working directory, which is `/workspace`.

**Rationale**: Errand skills are already `SKILL.md` files with name/description frontmatter — the same format — so bridging is a copy, not a translation. Without it, every skill the profile selected (including the system skill sets: gws, cloud-storage, hindsight, repo-context, binary-files) is invisible to Claude.

### 9. Result delivery reuses the existing contract

**Decision**: The transformer synthesises `TaskRunnerOutput` from the `result` event (`status: "completed"`, `result: <result text>`) and passes it through the existing `write_output_file()` and `post_result_callback()` path. If Claude called errand's `submit_result` MCP tool, that payload wins — including `status: "needs_input"` with questions.

**Rationale**: Deterministic. The default loop depends on the model choosing to call `submit_result`; here the CLI always emits a terminal `result` event, so the output does not hinge on model compliance. Honouring `submit_result` when present preserves the `needs_input` flow, which has no other equivalent.

### 10. Runtime allowlist, not a K8s denylist

**Decision**: The claude image is permitted when `CONTAINER_RUNTIME` is `docker` or `apple`, and rejected otherwise. The backend exposes `claude_supported` so the profile editor can hide the option.

**Rationale**: Running a personal subscription on shared cluster infrastructure crosses a ToS line. An allowlist stays correct when a fourth runtime is added; the original denylist on the literal string `kubernetes` would silently admit it.

## Risks / Trade-offs

- **[Reduced safety nets]** The claude path has no compaction hook, no stall guard, no XML/Harmony tool-call recovery, no file-mutation queue, and no mid-task Google token refresh — that refresh lives in the runner's `execute_command` wrapper, which Claude's own Bash tool bypasses, so a long task can lose Google auth mid-flight with no recovery → Mitigation: documented as a requirement in `claude-delegation` and surfaced in the Settings disclaimer; Claude Code brings its own compaction and turn limits.
- **[Per-task knobs do not apply]** `MAX_TURNS`, `LLM_REQUEST_TIMEOUT`, and the profile's LLM provider have no effect under `claude -p`; only `--effort` maps to `REASONING_EFFORT` → Mitigation: the profile editor disables the inapplicable fields when the claude image is selected.
- **[`--bare` becomes the `-p` default]** It never reads OAuth, so the token path would break → Mitigation: pin the CLI version, and add a smoke test asserting a token-authenticated run succeeds on the pinned version.
- **[ToS enforcement]** Anthropic could restrict `CLAUDE_CODE_OAUTH_TOKEN` in containers → Mitigation: opt-in with explicit disclaimers, using the official binary as the GitHub Action does.
- **[Rate limiting]** Concurrent tasks share one subscription quota → Mitigation: the user's responsibility, stated in the disclaimer; failures now surface as task failures rather than silent re-runs (decision 2).
- **[Image size]** +358 MB over the base → Mitigation: separate image; non-claude users are unaffected.
- **[CLI format drift]** The stream schema is not a stable API → Mitigation: pin `CLAUDE_CODE_VERSION`; unrecognised events degrade to `raw`; transformer tests are built from captured fixtures of the pinned version.
- **[bash in the image]** Re-introduces a shell the base deliberately dropped → Mitigation: confined to the claude variant; the default image is unchanged.
