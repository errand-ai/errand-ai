## 1. Cloud Dispatch Integration

- [x] 1.1 Add `elif integration == "github" and endpoint_type == "webhook"` branch in `dispatch_cloud_webhook()` that extracts `trigger_id` and `headers`, then calls `_dispatch_github_webhook()`
- [x] 1.2 Implement `_dispatch_github_webhook(body, headers, trigger_id)` following the `_dispatch_jira_webhook` pattern: validate trigger_id UUID, load trigger, check enabled, re-verify HMAC, call handler
- [x] 1.3 Use `x-hub-signature-256` (not `x-hub-signature`) when extracting the signature header for re-verification
- [x] 1.4 Call `handle_github_webhook(trigger, body, headers)` from `platforms.github.handler` on successful verification

## 2. Tests

- [x] 2.1 Test GitHub webhook relay dispatches to handler with valid trigger_id and signature
- [x] 2.2 Test missing trigger_id logs warning and discards
- [x] 2.3 Test invalid (non-UUID) trigger_id logs warning and discards
- [x] 2.4 Test trigger not found logs warning and discards
- [x] 2.5 Test disabled trigger logs warning and discards
- [x] 2.6 Test HMAC re-verification failure discards message
- [x] 2.7 Test missing signature header with secret-bearing trigger discards message
