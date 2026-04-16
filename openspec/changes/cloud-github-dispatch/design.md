## Context

`cloud_dispatch.py` routes webhook payloads from the errand-cloud WebSocket relay. It currently handles Slack (three endpoint types) and Jira (webhook type with HMAC re-verification). The Jira dispatcher (`_dispatch_jira_webhook`) follows this pattern:

1. Validate `trigger_id` is present and is a valid UUID
2. Load `WebhookTrigger` from the database
3. Check trigger exists and is enabled
4. Re-verify HMAC signature for defense in depth
5. Call the platform-specific handler

GitHub dispatch follows the identical pattern, differing only in the signature header name and the handler function called.

## Goals / Non-Goals

**Goals:**
- Add GitHub webhook dispatch to `cloud_dispatch.py` following the established Jira pattern
- Re-verify HMAC using the `X-Hub-Signature-256` header from the forwarded headers
- Call the existing `handle_github_webhook(trigger, body, headers)` handler

**Non-Goals:**
- Refactoring Jira and GitHub dispatch into a shared function (same reasoning as the cloud-side: keep separate until a third integration arrives)
- Changes to `handle_github_webhook` or `webhook_receiver.py` (already complete)

## Decisions

### 1. Mirror the Jira dispatch pattern exactly

`_dispatch_github_webhook()` is a copy of `_dispatch_jira_webhook()` with two changes:
- Reads `x-hub-signature-256` instead of `x-hub-signature` from forwarded headers
- Calls `handle_github_webhook()` instead of `handle_jira_webhook()`

**Rationale:** Consistency with the established pattern. The functions are short (~50 lines) and may diverge if GitHub dispatch needs additional logic (e.g. event type filtering).

## Risks / Trade-offs

- **Code duplication** → Accepted; both functions are short and may diverge. Extract if a third integration arrives.
