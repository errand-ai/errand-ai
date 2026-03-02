# Spec: PR #72 Review Fixes

## Requirement: XSS Prevention in Cloud Callback
The `_close_popup()` helper in `main.py` SHALL HTML-escape all interpolated values using `html.escape()` before embedding them in the HTML response.

#### Scenario: Error parameter contains script tag
- **GIVEN** the callback receives `?error=<script>alert(1)</script>`
- **THEN** the HTML response SHALL contain the escaped text, not executable script

## Requirement: CSRF State on Cloud Login
The cloud login endpoint SHALL generate a random state token, store it server-side, include it in the redirect URL to errand-cloud, and the callback SHALL validate it before processing the code.

#### Scenario: Callback without valid state
- **GIVEN** a callback request with a missing or invalid state parameter
- **THEN** the response SHALL close the popup with an error message

## Requirement: Accurate Cloud Status
The `/api/cloud/status` endpoint SHALL reflect the live WebSocket connection state, not just the database credential status.

#### Scenario: Credentials exist but WebSocket is disconnected
- **GIVEN** cloud credentials with status "connected" in DB but WebSocket not connected
- **THEN** the status endpoint SHALL return `disconnected`

## Requirement: Disconnect Event Accuracy
The disconnect endpoint SHALL publish `not_configured` when no credentials existed prior to the disconnect call.

## Requirement: Endpoint Sync on Existing
When `try_register_endpoints` finds endpoints already registered on errand-cloud, it SHALL persist them to the local `cloud_endpoints` setting.

## Requirement: Code Cleanup
- Remove unused imports: `os` from `cloud_auth.py`, `pytest` from `test_cloud_auth.py`, `MagicMock` from `test_cloud_routes.py`
- Add explanatory comments to `except CancelledError: pass` blocks in `cloud_client.py`
- Rename `response_url_callback` to `use_response_url` in `slack/routes.py`
- Fix `admin-settings-api` spec wire format to show `task` wrapper
