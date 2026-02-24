## Context

The task-runner container currently includes git, ssh, curl, and busybox on a distroless Python base image. The agent can execute shell commands via `execute_command` but lacks `gh` (GitHub CLI) and `openspec` (Node.js-based CLI). Adding these enables the agent to interact with GitHub and manage OpenSpec artifacts within cloned repos.

GitHub authentication must be injected securely. The project already has a platform integration system (registry, encrypted credentials, verify lifecycle) used by Twitter. GitHub will follow the same pattern, appearing on the Integrations settings sub-page.

The worker currently injects credentials from the admin settings `credentials` list (simple key/value pairs) into container env vars. The GitHub integration uses the platform credential system instead, with the worker loading and processing GitHub credentials separately during task preparation.

## Goals / Non-Goals

**Goals:**
- Add `gh` and `openspec` binaries to the task-runner image while keeping distroless base
- Support two GitHub auth modes: PAT (simple) and GitHub App (ephemeral tokens)
- Follow the existing platform integration pattern for configuration and UI
- Only inject `GH_TOKEN` when the GitHub integration is enabled and connected

**Non-Goals:**
- Per-task repository scoping for GitHub App tokens (use installation-wide scope for now)
- Token refresh mid-task (1-hour TTL is sufficient for current task durations)
- GitHub webhook handling or GitHub-triggered task creation
- Making openspec available outside the task-runner container

## Decisions

### 1. gh CLI: Static binary in git-builder stage

Download the gh tarball in the existing `git-builder` stage and copy the binary to the final image. Go binaries are statically linked — no shared library staging needed.

Use a build arg for the version and `TARGETARCH` for multi-arch support.

**Why not a separate stage?** gh is a single binary with no dependencies. Adding it to the existing builder avoids an extra stage for one file.

### 2. openspec + Node.js: New node-builder stage

Add a `node-builder` stage using `node:22-bookworm-slim` to `npm install -g @fission-ai/openspec@latest`. Copy the node binary, the global node_modules, and the openspec symlink into the final distroless image.

Both the node builder and the distroless final image are bookworm-based, so glibc and shared libraries are compatible. Node's runtime dependencies (libstdc++, etc.) are present in the distroless python image since both are built on the same Debian base.

**Alternatives considered:**
- *Switch to non-distroless base*: Loses security benefits, larger attack surface.
- *Bundle openspec as a single executable (pkg/SEA)*: Fragile, depends on openspec internals, maintenance burden.
- *Mount openspec as a volume*: Operational complexity, version drift, doesn't work cleanly across Docker/K8s runtimes.

**Trade-off:** ~100-120MB image size increase for node binary + openspec package. Acceptable given the capability it provides.

### 3. GitHub as a platform integration

Register a `GitHubPlatform` class in `errand/platforms/github.py` following the same pattern as `TwitterPlatform`. The platform appears on the Integrations settings sub-page alongside Twitter.

The credential schema is dynamic based on auth mode:
- **PAT mode**: Single field — `personal_access_token`
- **App mode**: Three fields — `app_id`, `private_key` (PEM), `installation_id`

Both modes store an `auth_mode` field (`pat` or `app`) in the encrypted credential data to distinguish them.

**Credential verification:**
- PAT: `GET /user` with the token — checks it's valid and has access
- App: Mint a test installation token using the JWT flow — confirms the app ID, key, and installation ID are correct

### 4. Worker-side token injection

During `process_task_in_container`, after building `env_vars`, the worker checks if the GitHub platform credential exists and is connected:

- **PAT mode**: Read the decrypted `personal_access_token` and set `env_vars["GH_TOKEN"]`
- **App mode**: Mint an ephemeral installation access token by:
  1. Creating a JWT signed with the app's private key (RS256, 10-min expiry)
  2. POSTing to `https://api.github.com/app/installations/{installation_id}/access_tokens`
  3. Extracting the `token` from the response (1-hour TTL)
  4. Setting `env_vars["GH_TOKEN"]` to the minted token

If the GitHub integration is not configured or not connected, no `GH_TOKEN` is injected — the agent simply won't have GitHub access, and `gh` commands will fail with a clear auth error.

**Why mint in the worker, not the container?** The app private key never enters the container. The worker holds the secret and only passes an ephemeral, scoped token. A leaked container token expires in 1 hour; a leaked private key would grant indefinite access.

### 5. No new Python dependencies

JWT creation uses `PyJWT` (already present for local auth). RS256 signing uses `cryptography` (already present for Fernet credential encryption). The GitHub API call uses `httpx` or the stdlib `urllib` — the worker already has httpx available.

## Risks / Trade-offs

- **Image size increase (~100-120MB)**: Node.js binary is large. → Acceptable for the capability. Could revisit with openspec standalone builds if they become available.
- **Node.js shared library compatibility**: Copying node from bookworm-slim into distroless python3-debian12. → Both are bookworm-based. Test with `docker build` + `docker run node --version` to verify.
- **GitHub App token expiry**: Tokens last 1 hour, cannot be extended. → Sufficient for current task durations. If tasks grow longer, add an MCP tool for token refresh in a future change.
- **openspec version drift**: npm install at build time pins to whatever `latest` is. → Pin version via build arg, same as gh version.

## Migration Plan

- No database migration needed — GitHub credentials use the existing `platform_credentials` table
- No breaking changes — this is purely additive
- Rollback: Remove the GitHub platform registration and the node-builder stage from Dockerfile
- Deploy order: Image must be built first (contains new binaries), then backend (registers platform), then frontend (shows UI)

## Open Questions

None — all decisions made during explore phase.
