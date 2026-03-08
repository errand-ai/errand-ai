## 1. Backend OAuth Routes

- [x] 1.1 Create integration_routes.py with provider configuration (Google: token URL, scopes, userinfo URL; Microsoft: token URL, scopes, Graph /me URL)
- [x] 1.2 Implement GET /api/integrations/{provider}/authorize — build OAuth URL, redirect to consent screen
- [x] 1.3 Implement GET /api/integrations/{provider}/callback — exchange code for tokens, fetch user info, encrypt and store in PlatformCredential
- [x] 1.4 Implement DELETE /api/integrations/{provider} — delete PlatformCredential record
- [x] 1.5 Implement GET /api/integrations/status — return availability and connection status for all providers
- [x] 1.6 Register integration routes in main.py
- [x] 1.7 Write tests for all integration routes (mock OAuth token exchange, mock user info endpoints)

## 2. Token Refresh

- [x] 2.1 Create cloud_storage.py utility module with token refresh functions for Google and Microsoft
- [x] 2.2 Implement refresh logic: check expires_at (5-min buffer), POST to token endpoint with refresh_token, update PlatformCredential
- [x] 2.3 Handle refresh failures gracefully (log warning, return None, don't block task execution)
- [x] 2.4 Write tests for token refresh (expired token, valid token, revoked refresh token)

## 3. Worker MCP Injection

- [x] 3.1 Add GDRIVE_MCP_URL and ONEDRIVE_MCP_URL env var reads to worker.py
- [x] 3.2 Load cloud storage credentials in process_task_in_container (using existing load_credentials pattern)
- [x] 3.3 Call token refresh before injection
- [x] 3.4 Inject google_drive and/or onedrive into mcp_servers dict with Bearer token header (two-gate pattern: URL set AND credentials exist)
- [x] 3.5 Ensure cloud storage servers participate in _profile_mcp_servers filtering
- [x] 3.6 Write tests for worker injection logic (both gates, single gate, profile filtering)

## 4. System Prompt

- [x] 4.1 Add cloud storage instructions constant to worker.py (tools overview, ETag pattern, error handling, download-modify-upload workflow)
- [x] 4.2 Append instructions to system prompt only when at least one cloud storage MCP server is injected
- [x] 4.3 Write test confirming prompt injection conditional on cloud storage presence

## 5. Frontend Integration UI

- [x] 5.1 Create CloudStorageIntegration.vue component with provider cards (Google Drive, OneDrive)
- [x] 5.2 Fetch integration status from GET /api/integrations/status on mount
- [x] 5.3 Implement "Connect" button (redirect to /api/integrations/{provider}/authorize)
- [x] 5.4 Implement "Disconnect" button (DELETE /api/integrations/{provider}, refresh status)
- [x] 5.5 Handle greyed-out state when provider is not available
- [x] 5.6 Display connected user email/name when connected
- [x] 5.7 Add cloud storage section to SettingsPage.vue
- [x] 5.8 Write component tests for all states (available/unavailable, connected/disconnected)

## 6. Helm Chart

- [x] 6.1 Add gdrive and onedrive sections to values.yaml (enabled, image, port, existingSecret)
- [x] 6.2 Create gdrive-mcp-deployment.yaml template (conditional on gdrive.enabled)
- [x] 6.3 Create gdrive-mcp-service.yaml template (ClusterIP, conditional)
- [x] 6.4 Create onedrive-mcp-deployment.yaml template (conditional on onedrive.enabled)
- [x] 6.5 Create onedrive-mcp-service.yaml template (ClusterIP, conditional)
- [x] 6.6 Inject GDRIVE_MCP_URL into server-deployment.yaml and worker-deployment.yaml (conditional)
- [x] 6.7 Inject ONEDRIVE_MCP_URL into server-deployment.yaml and worker-deployment.yaml (conditional)
- [x] 6.8 Inject Google OAuth client credentials from secret into server-deployment.yaml (conditional)
- [x] 6.9 Inject Microsoft OAuth client credentials from secret into server-deployment.yaml (conditional)
- [x] 6.10 Verify helm template renders correctly with all combinations (both enabled, one enabled, both disabled)

## 7. Docker Compose (Local Dev)

- [x] 7.1 Add gdrive-mcp-server and onedrive-mcp-server services to docker-compose.yml
- [x] 7.2 Pass GDRIVE_MCP_URL and ONEDRIVE_MCP_URL to errand and worker services
- [x] 7.3 Add Google/Microsoft client credential env vars to errand service
- [x] 7.4 Verify full stack works with cloud storage MCP servers via docker compose up --build
