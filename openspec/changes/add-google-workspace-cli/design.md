## Context

The task-runner currently accesses Google Drive through a separate `gdrive-mcp` container that acts as an MCP server. The errand server injects the MCP server URL and an OAuth Bearer token into the task container's `mcp.json`. Google has released the Google Workspace CLI (`gws`), a Rust binary providing unified access to all Workspace APIs. It accepts pre-obtained OAuth tokens via the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable and ships with agent skills in `SKILL.md` format — identical to the format the task-runner already supports.

The Settings UI currently groups Google Drive under "Cloud Storage" alongside OneDrive. This change moves Google into its own "Google Workspace" section.

**Prerequisite:** The `task-generators-page` change must be merged first. It extracts email task-generation settings into a dedicated Task Generators page and refactors the email poller to read from the new `TaskGenerator` model.

## Goals / Non-Goals

**Goals:**

- Replace `gdrive-mcp` with `gws` CLI binary installed in the task-runner image
- Give task-runner agents access to the full Google Workspace (Drive, Gmail, Calendar, Sheets, Docs, Chat)
- Generate gws agent skills at image build time using `gws generate-skills` (fetches Google Discovery API)
- Conditionally inject gws skills only when Google token is available
- Introduce a system skills layer baked into the task-runner image
- Restructure Settings UI to reflect the expanded Google integration

**Non-Goals:**

- Replacing OneDrive MCP server (gws doesn't cover Microsoft services)
- Building an MCP wrapper around gws (shell execution is sufficient)
- Adding GitHub webhook or generic webhook triggers (future change)
- Refactoring the system prompt into on-demand skills (separate change)
- Implementing incremental OAuth scope requests (all scopes requested upfront)
- Task Generators page or email poller changes (handled by `task-generators-page` change)

## Decisions

### D1: Token injection via environment variable (not MCP)

The gws CLI reads `GOOGLE_WORKSPACE_CLI_TOKEN` from the environment. Instead of injecting a Google Drive entry into `mcp.json` with an Authorization header, the task manager will set this env var on the task container.

**Alternative considered:** Wrapping gws in a custom MCP server for structured tool definitions. Rejected because (a) the agent already has shell access and gws outputs JSON, (b) the gws skills provide natural-language instructions that are equivalent to MCP tool schemas for LLM usage, and (c) adding an MCP wrapper increases complexity without clear benefit.

### D2: Build-time skill bundling from upstream repo

The `googleworkspace/cli` repository ships ~100 pre-authored agent skills (SKILL.md files) under `skills/gws-*` that are versioned alongside the CLI binary. There is no separate `gws generate-skills` command — skills are pre-authored and tagged with each release. At image build time we download the `gws` binary from the GitHub release tarball (matching `${GWS_VERSION}` and `TARGETARCH`) and clone the upstream repo at the matching `v${GWS_VERSION}` tag to copy `skills/gws-*` into the image. The release tarball is preferred over `npm install -g @googleworkspace/cli` because the distroless final image cannot run npm wrappers and the release binary is a self-contained Rust executable.

**Alternative considered:** Installing skills via `npx skills add https://github.com/googleworkspace/cli`. Rejected because that command writes to user home directories at runtime, while we need a deterministic, repeatable build into a known path.

**Trade-off:** Requires network access to `github.com` during Docker build. This is acceptable since the build already downloads npm packages and other dependencies.

### D3: System skills at `/opt/system-skills/` with runtime merge

System skills (gws skills and future CLI tool skills) will be baked into the task-runner image at `/opt/system-skills/`. At task preparation time, `task_manager.py` will read system skills from the running container (via a known list or image metadata) and merge them into the skills archive with lowest precedence: DB > git > system.

**Approach:** The task manager will maintain a registry of system skill sets (e.g., `gws`) with their conditions (e.g., "Google token present"). When conditions are met, the corresponding skills from `/opt/system-skills/` are included in the tar archive sent to the container.

**Alternative considered:** Having the task-runner agent discover system skills at startup by scanning `/opt/system-skills/`. Rejected because (a) the skill manifest in the system prompt needs to be built by the task manager before the container starts, and (b) conditional inclusion (only when token is present) must happen before injection.

**Implementation:** Since the task manager runs on the server (not inside the task-runner container), it cannot directly read `/opt/system-skills/` from the image. Instead:
- At image build time, generate a `system-skills-manifest.json` alongside the skills, listing all system skill names, descriptions, and file paths.
- The errand server's `task_manager.py` will shell out to the container runtime to read the manifest from the task-runner image (Docker: `docker run --rm <image> cat /opt/system-skills/manifest.json`; K8s: read from a shared ConfigMap or embed in the server image).
- **Simpler alternative (chosen):** Bundle the gws skills directly into the errand server image as well, at a known path (e.g., `/app/system-skills/gws/`). The task manager reads them locally and includes them in the skills tar. When the task-runner image is updated, the server image is also rebuilt (same CI pipeline), keeping them in sync.

### D4: Flat skill directory structure

All skills (system, git, DB) will be merged into a flat `/workspace/skills/` directory. The gws skills already use a flat sibling structure with relative path cross-references (e.g., `../gws-shared/SKILL.md`). Introducing subdirectories would break these references.

### D5: Expanded OAuth scopes — all upfront

The Google OAuth flow will request a comprehensive set of scopes covering Drive, Gmail (modify), Calendar, Sheets, Docs, and other Workspace services. All scopes are requested during the initial authorization. Users who previously authorized with Drive-only scope will see a re-authorization prompt when the UI detects stale scopes.

**Scopes:**
```
openid email profile
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/chat.messages
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/contacts.readonly
```

**Alternative considered:** Incremental scope requests (ask only when a service is needed). Rejected because Google's incremental auth can invalidate previous refresh tokens, adding complexity to token management without clear UX benefit — users connecting Google Workspace expect broad access.

### D6: Google Workspace settings UI — new section on Integrations page

Google Drive moves out of the "Cloud Storage" section into a new "Google Workspace" section on the Integrations page. This section shows:
- Connection status and connected user
- A list of available services (Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks) as informational badges
- Connect/Disconnect button

The Cloud Storage section retains OneDrive only.

## Risks / Trade-offs

**[Build-time network dependency]** → `gws generate-skills` requires network access to Google's Discovery API during Docker build. Mitigation: Build infrastructure already has internet access; can cache/vendor skills as fallback if Discovery API is down.

**[Scope breadth may concern users]** → Requesting Gmail, Calendar, etc. scopes upfront is a large permission ask. Mitigation: The Google Workspace section in Settings clearly lists what services are enabled, and the broad scope is justified by the CLI's capabilities. Users who don't want broad access can simply not connect.

**[Stale-scope token detection]** → Existing users have Drive-only refresh tokens. Mitigation: Store granted scopes in `PlatformCredential` metadata; compare against required scopes and show "Re-authorize" prompt in UI when stale.

**[gws binary size]** → Adding a Rust binary to the distroless image increases image size. Mitigation: The binary is a single static file; the size increase is modest compared to the complexity removed (entire gdrive-mcp container + service).

**[Breaking change: GDRIVE_MCP_URL removal]** → Deployments using `GDRIVE_MCP_URL` will need updating. Mitigation: Clear documentation; env var simply becomes unused (no crash, just no Google Drive MCP injection).

## Migration Plan

1. **Prerequisite**: Merge `task-generators-page` change first (Task Generators page, email poller refactor, email credential simplification).
2. **Helm chart**: Remove `gdrive-mcp` Deployment and Service templates. Remove `GDRIVE_MCP_URL` from server deployment env vars. Keep Google OAuth secret injection (still needed for OAuth flow).
3. **Docker Compose**: Remove `gdrive-mcp` service from both `testing/docker-compose.yml` and `deploy/docker-compose.yml`.
4. **ArgoCD values**: Remove any `gdrive` MCP URL overrides from ArgoCD values file. The `gdrive.enabled` Helm value becomes unused (can be removed or kept for backwards compat).
5. **Existing users**: Users with Google Drive connected will need to re-authorize to get expanded scopes. The UI will detect stale scopes and prompt.
6. **Rollback**: If issues arise, re-add `gdrive-mcp` service and restore MCP injection logic. The OAuth credentials are unchanged.

## Open Questions

- **Which gws skills to include?** All 92 skills (services, helpers, personas, recipes, workflows) or a curated subset (services + helpers only, ~36 skills)? Including all adds context but most tasks won't use persona or recipe skills.
- **gws binary distribution for distroless image**: The npm install includes pre-built binaries, but the distroless image has no package manager. Need to verify the binary can be copied standalone from the npm install stage.
