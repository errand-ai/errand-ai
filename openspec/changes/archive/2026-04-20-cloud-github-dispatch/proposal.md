## Why

The `github-projects-integration` change added a direct webhook receiver for GitHub (`POST /webhooks/github`) and the full handler pipeline (`handle_github_webhook`). However, `cloud_dispatch.py` — the module that routes webhook payloads received via the errand-cloud WebSocket relay — does not yet recognise `integration="github"`. Cloud-relayed GitHub webhooks are currently logged as "Unknown cloud webhook integration" and discarded.

With the corresponding `github-webhook-endpoint` change shipping on errand-cloud (adding `POST /webhooks/github` to the relay service), the desktop app needs to handle these relayed payloads.

## What Changes

- Add `elif integration == "github" and endpoint_type == "webhook"` branch in `dispatch_cloud_webhook()`
- Implement `_dispatch_github_webhook()` following the same pattern as `_dispatch_jira_webhook()`: look up trigger by `trigger_id`, re-verify HMAC using `X-Hub-Signature-256`, call `handle_github_webhook()`
- Use `X-Hub-Signature-256` header (not `X-Hub-Signature`) for re-verification, matching GitHub's signature header name

## Capabilities

### New Capabilities
- `cloud-github-dispatch`: Route GitHub webhook payloads received via errand-cloud relay to the GitHub webhook handler

### Modified Capabilities

## Impact

- `errand/cloud_dispatch.py` — add GitHub dispatch branch and `_dispatch_github_webhook()` function
- No new dependencies — `handle_github_webhook` and `_verify_hmac` already exist
- No database changes
