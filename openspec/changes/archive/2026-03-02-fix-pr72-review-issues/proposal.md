# Proposal: Fix PR #72 Review Issues

## Problem

Copilot code review on PR #72 (add-cloud-relay-integration) raised 11 issues across security, correctness, and code quality. Two are security vulnerabilities (reflected XSS in popup callback, missing CSRF state on cloud login), three are functional bugs (disconnect event for unconfigured instances, stale cloud status from DB, missing endpoint sync), and the rest are code cleanup.

## Solution

Address all 11 review findings in a single patch:

- **Security**: HTML-escape the popup callback response to prevent reflected XSS. Add CSRF state parameter to the cloud login/callback flow.
- **Bug fixes**: Publish `not_configured` instead of `disconnected` when no credentials existed. Track live WebSocket connection state for accurate `/api/cloud/status`. Persist existing cloud endpoints to local setting in `try_register_endpoints`.
- **Cleanup**: Remove unused imports (`os`, `pytest`, `MagicMock`). Add comments to `except CancelledError: pass` blocks. Rename `response_url_callback` parameter to `use_response_url`. Fix spec wire format documentation.

## Impact

- **Files modified**: `main.py`, `cloud_client.py`, `cloud_auth.py`, `cloud_endpoints.py`, `platforms/slack/routes.py`, `tests/test_cloud_auth.py`, `tests/test_cloud_routes.py`, `openspec/specs/admin-settings-api/spec.md`
- **Risk**: Low — mostly cleanup and targeted fixes, no architectural changes
- **Tests**: Update existing tests for changed behavior (disconnect event, status endpoint)
