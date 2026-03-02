# Tasks: Fix PR #72 Review Issues

## Security Fixes

- [x] HTML-escape values in `_close_popup()` in `main.py` using `html.escape()` for both `message` and `error` parameters
- [x] Add CSRF state to cloud login: generate nonce in `/api/cloud/auth/login`, store in DB, include in redirect URL
- [x] Validate CSRF state in `/api/cloud/auth/callback`: check nonce matches and delete after use
- [x] Update cloud login test to verify state parameter is included in redirect URL
- [x] Update cloud callback tests for state validation (missing state, invalid state, valid state)

## Bug Fixes

- [x] Fix disconnect endpoint to publish `not_configured` event when no credentials existed
- [x] Add `is_connected()` function to `cloud_client.py` that exposes live WebSocket connection state
- [x] Update `/api/cloud/status` endpoint to check live WebSocket state and return `disconnected` when credentials exist but WebSocket is not connected
- [x] Update `try_register_endpoints` in `cloud_endpoints.py` to persist existing endpoints to local `cloud_endpoints` setting when they already exist on errand-cloud
- [x] Update disconnect and status tests for changed behavior

## Code Cleanup

- [x] Remove unused `import os` from `cloud_auth.py`
- [x] Remove unused `import pytest` from `tests/test_cloud_auth.py`
- [x] Remove unused `MagicMock` from import in `tests/test_cloud_routes.py`
- [x] Add explanatory comments to both `except CancelledError: pass` blocks in `cloud_client.py` `stop_cloud_client()`
- [x] Rename `response_url_callback` parameter to `use_response_url` in `slack/routes.py` and update all callers
- [x] Fix `admin-settings-api` spec wire format to show `task` wrapper around cloud_status event data
