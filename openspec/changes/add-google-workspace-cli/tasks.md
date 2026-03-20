## 1. Task Runner Image — gws CLI

- [ ] 1.1 Add gws-builder stage to `task-runner/Dockerfile`: install gws CLI (npm or cargo), run `gws generate-skills --output-dir /gws-skills/`, copy binary and skills to final image at `/usr/local/bin/gws` and `/opt/system-skills/gws/`
- [ ] 1.2 Add gws-builder stage to main `Dockerfile` (errand server): copy generated gws skills to `/app/system-skills/gws/` so task_manager can read them locally
- [ ] 1.3 Verify gws binary runs in distroless image (check shared library dependencies)
- [ ] 1.4 Add `GWS_VERSION` build arg with sensible default

## 2. Backend — Google Token Injection

- [ ] 2.1 Modify `task_manager.py`: inject `GOOGLE_WORKSPACE_CLI_TOKEN` env var on task container when Google credentials exist (refresh token if expired before injection)
- [ ] 2.2 Remove Google Drive MCP injection from `task_manager.py` (remove `google_drive` entry from mcp.json building logic, keep OneDrive)
- [ ] 2.3 Remove Google Drive system prompt instructions from cloud storage injection (keep OneDrive instructions)
- [ ] 2.4 Update `container_runtime.py` if needed to pass additional env vars to containers

## 3. Backend — System Skills Loading

- [ ] 3.1 Add `load_system_skills()` function to `task_manager.py`: reads SKILL.md files from `/app/system-skills/gws/` directory, returns list of skill dicts
- [ ] 3.2 Add conditional logic: only load gws system skills when Google token is present for the task
- [ ] 3.3 Update `merge_skills()` to support three-way merge: DB > git > system
- [ ] 3.4 Update `build_skills_archive()` and skill manifest to include system skills

## 4. Backend — OAuth Scope Expansion

- [ ] 4.1 Update Google OAuth scopes in `integration_routes.py` to include drive, gmail.modify, calendar, spreadsheets, documents, chat.messages, tasks, contacts.readonly
- [ ] 4.2 Store granted scopes in `PlatformCredential` metadata on OAuth callback
- [ ] 4.3 Add `reauth_required` field to integration status endpoint (compare stored scopes vs required scopes)
- [ ] 4.4 Remove `GDRIVE_MCP_URL` dependency from Google integration status mode resolution

## 5. Frontend — Google Workspace Settings Section

- [ ] 5.1 Add "Google Workspace" section to Integrations page with connection status, connect/disconnect button, and re-authorize button (when `reauth_required`)
- [ ] 5.2 Add service badges display (Drive, Gmail, Calendar, Sheets, Docs, Chat, Tasks, Contacts) with active/muted styling based on connection state
- [ ] 5.3 Remove Google Drive card from Cloud Storage section (keep OneDrive only)
- [ ] 5.4 Update integration status API calls to handle new Google Workspace response format

## 6. Helm and Docker Compose Cleanup

- [ ] 6.1 Remove `gdrive-mcp` service from `testing/docker-compose.yml`
- [ ] 6.2 Remove `gdrive-mcp` service from `deploy/docker-compose.yml`
- [ ] 6.3 Delete `helm/errand/templates/gdrive-mcp-deployment.yaml`
- [ ] 6.4 Delete `helm/errand/templates/gdrive-mcp-service.yaml`
- [ ] 6.5 Remove `GDRIVE_MCP_URL` env var from `helm/errand/templates/server-deployment.yaml`
- [ ] 6.6 Update `helm/errand/values.yaml`: remove gdrive MCP server config (keep OAuth secret reference)

## 7. Tests

- [ ] 7.1 Update `test_worker.py` / `test_task_manager.py`: test Google token env var injection instead of MCP injection
- [ ] 7.2 Add tests for system skills loading and three-way merge (DB > git > system)
- [ ] 7.3 Add tests for expanded OAuth scope storage and stale-scope detection
- [ ] 7.4 Update frontend tests for Google Workspace section

## 8. Documentation and VERSION

- [ ] 8.1 Bump VERSION file (minor version — new feature)
- [ ] 8.2 Update CLAUDE.md: document gws CLI in task-runner, remove gdrive-mcp references
