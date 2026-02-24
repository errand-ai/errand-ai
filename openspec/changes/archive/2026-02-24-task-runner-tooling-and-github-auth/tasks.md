## 1. Task Runner Image — gh CLI

- [x] 1.1 Add `GH_VERSION` build arg and `TARGETARCH` to git-builder stage, download gh tarball and extract binary to `/usr/local/bin/gh`
- [x] 1.2 Add `COPY --from=git-builder /usr/local/bin/gh /usr/local/bin/gh` to final stage
- [x] 1.3 Verify `gh --version` works in built container

## 2. Task Runner Image — Node.js + openspec

- [x] 2.1 Add `node-builder` stage from `node:22-bookworm-slim`, run `npm install -g @fission-ai/openspec@latest`
- [x] 2.2 Copy node binary from node-builder to final stage (`/usr/local/bin/node`)
- [x] 2.3 Copy global node_modules and openspec symlink from node-builder to final stage
- [x] 2.4 Verify `node --version` and `openspec --version` work in built container

## 3. GitHub Platform Module

- [x] 3.1 Create `errand/platforms/github.py` with `GitHubPlatform` class extending `Platform`
- [x] 3.2 Implement `info()` returning platform id, label, and credential schema with `auth_mode` selector, PAT fields, and App fields
- [x] 3.3 Implement `verify_credentials()` for PAT mode — `GET /user` with the token
- [x] 3.4 Implement `verify_credentials()` for App mode — mint test installation token via JWT flow
- [x] 3.5 Implement `mint_installation_token(app_id, private_key, installation_id)` standalone function
- [x] 3.6 Register `GitHubPlatform` in the platform registry at app startup in `main.py`
- [x] 3.7 Write tests for PAT verification (mock HTTP responses)
- [x] 3.8 Write tests for App verification and token minting (mock HTTP responses and JWT creation)

## 4. Worker — GitHub Token Injection

- [x] 4.1 Add GitHub credential loading in `process_task_in_container` — check if GitHub platform credential is connected
- [x] 4.2 For PAT mode, decrypt and set `env_vars["GH_TOKEN"]` to the `personal_access_token` value
- [x] 4.3 For App mode, call `mint_installation_token()` and set `env_vars["GH_TOKEN"]` to the returned token
- [x] 4.4 Handle minting failures gracefully — log warning, skip `GH_TOKEN`, continue with task
- [x] 4.5 Write tests for PAT token injection (mock platform credential load)
- [x] 4.6 Write tests for App token injection (mock `mint_installation_token`)
- [x] 4.7 Write test for no injection when integration is disconnected/missing

## 5. Frontend — GitHub Integration Card

- [x] 5.1 Add GitHub integration card component to the Integrations settings sub-page
- [x] 5.2 Implement auth mode selector (PAT / GitHub App) that toggles visible credential fields
- [x] 5.3 PAT mode: show personal access token password field
- [x] 5.4 App mode: show App ID text field, Private Key textarea, Installation ID text field
- [x] 5.5 Wire Save/Connect button to `PUT /api/platforms/github/credentials` with `auth_mode` and relevant fields
- [x] 5.6 Wire Disconnect button to `DELETE /api/platforms/github/credentials`
- [x] 5.7 Show connection status (connected/disconnected) from platform credential status
- [x] 5.8 Write frontend tests for auth mode toggling and form submission

## 6. Integration Testing

- [x] 6.1 Build task-runner image and verify all new binaries are available (`gh`, `node`, `openspec`)
- [x] 6.2 Test end-to-end: configure GitHub PAT in settings, run a task, verify `GH_TOKEN` is present in container env
- [x] 6.3 Test end-to-end: configure GitHub App in settings, run a task, verify ephemeral token is minted and injected
