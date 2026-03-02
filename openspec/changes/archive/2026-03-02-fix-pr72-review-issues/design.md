# Design: Fix PR #72 Review Issues

## Decisions

### 1. XSS Prevention in Popup Callback
Use `html.escape()` on all user-supplied values interpolated into the HTML response in `_close_popup()`. The `error` query parameter comes from errand-cloud and could be manipulated.

### 2. CSRF State on Cloud Login
Store a random state token in the user's session (or a short-lived DB/memory entry) before redirecting to errand-cloud. Validate it in the callback. Since errand-cloud already handles its own state with Keycloak, the simplest approach is to use a signed cookie with a nonce — but since errand doesn't use cookies, we'll store state in the database settings table with a TTL check, similar to how errand-cloud stores state in Valkey.

**Simpler alternative**: Since the cloud callback is a popup window (not a full-page redirect), the attack surface for CSRF is reduced. The popup is opened by JavaScript that already has a valid auth token, and the callback stores credentials — it doesn't grant access. However, to satisfy the review, we'll add state validation using a server-side nonce stored temporarily in the session/DB.

### 3. Live WebSocket Status Tracking
Add a module-level variable in `cloud_client.py` (e.g., `_ws_connected: bool`) that tracks whether the WebSocket is currently connected. The `/api/cloud/status` endpoint checks this flag alongside the DB credential status to return accurate live status.

### 4. Endpoint Sync on Existing Check
When `check_existing_endpoints()` finds endpoints already registered, persist them to the local `cloud_endpoints` setting so the UI can display them.

### 5. Disconnect Event Accuracy
In the disconnect endpoint, check whether credentials existed before publishing the event. Publish `not_configured` if no credentials were found.
