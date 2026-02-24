## Why

The task-runner agent can execute shell commands but lacks the `gh` (GitHub CLI) and `openspec` binaries. Adding these enables the agent to interact with GitHub repositories (create PRs, list issues, check CI status) and manage OpenSpec artifacts directly within cloned repos. GitHub authentication needs to be injected securely into the container — supporting both simple PATs for quick setup and ephemeral GitHub App installation tokens for production use.

## What Changes

- Add `gh` CLI binary to the task-runner Docker image via the existing `git-builder` stage (single static Go binary, no new dependencies)
- Add a `node-builder` multi-stage build step to install Node.js and `openspec` CLI, copying the node binary and installed package into the distroless final image
- Add a "GitHub" platform integration on the Integrations settings sub-page, following the existing platform pattern (encrypted credentials, verify/connect/disconnect lifecycle)
- Support two auth modes within the GitHub integration: PAT (user provides a personal access token) or GitHub App (user provides app ID, private key, installation ID)
- Add worker-side logic to mint ephemeral GitHub App installation tokens (1-hour TTL) per task using JWT + RS256 when the GitHub App auth mode is configured
- Inject `GH_TOKEN` into the task-runner container environment **only when the GitHub integration is enabled and connected** — PAT value is used directly, or an ephemeral App token is minted per task

## Capabilities

### New Capabilities
- `github-integration`: GitHub platform integration — platform registration, credential storage (PAT or App mode), verification, and worker-side token injection/minting. Covers backend platform module, API endpoints, and Integrations sub-page UI.

### Modified Capabilities
- `task-runner-image`: Add gh CLI binary and Node.js + openspec CLI to the distroless container image via multi-stage build
- `task-worker`: Worker loads GitHub integration credentials at task time, mints ephemeral App tokens if configured, and injects GH_TOKEN into container env vars only when integration is enabled

## Impact

- **task-runner/Dockerfile**: New `node-builder` stage, gh binary download in `git-builder` stage, additional COPY directives in final stage. Image size increases ~100-120MB (node binary + openspec package).
- **errand/worker.py**: New function to mint GitHub App installation tokens (JWT creation + GitHub API call). Called during `process_task_in_container` if GitHub App settings are configured.
- **errand/platforms/**: New `github.py` platform module following the existing platform pattern (verify_credentials, credential fields).
- **errand/main.py**: GitHub platform registered alongside existing platforms; uses existing platform credential API endpoints.
- **frontend/src/pages/settings/**: GitHub integration card added to Integrations sub-page, with auth mode selector (PAT vs App) and corresponding credential fields.
- **Dependencies**: No new Python dependencies — PyJWT and cryptography are already present for local auth.
- **Helm chart**: New optional secret values for GitHub App credentials (app ID, private key, installation ID).
