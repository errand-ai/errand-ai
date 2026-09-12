## Context

Endpoint state lives in two places that can disagree: errand-cloud's `endpoints` table, and errand's local cache — the `cloud_endpoints` Setting for Slack, and `cloud_webhook_url` / `cloud_endpoint_token` columns on each `WebhookTrigger`.

Slack tolerates the disagreement because `try_register_endpoints` reconciles on every connect: it asks the cloud what exists and re-creates what does not. Webhook triggers have no equivalent. They are registered at trigger-save time and the local columns are then treated as permanent.

Both halves render into the same "Cloud Endpoints" list on the settings page, which is why the divergence was hard to spot: a stale trigger URL sits next to three freshly reconciled Slack URLs and looks identical.

The current spec records the absence of reconciliation as a deliberate non-goal: "the user must re-save the trigger to retry — the system does NOT auto-backfill on cloud reconnect". That was reasonable under the assumption it encodes — that the only way a trigger lacks a live endpoint is a registration that visibly failed, which the user can see and retry. Production disproved it. A registration that succeeded months ago can be revoked server-side by subscription machinery the user never interacts with, and the settings page reports it as healthy.

## Goals / Non-Goals

**Goals:**
- Detect webhook trigger endpoints that no longer exist on errand-cloud, and re-register them.
- Keep the local cache as the display source, so the page still works offline.
- Never display a URL that is known not to work.
- Serve Slack and webhook triggers from one existence-check helper.

**Non-Goals:**
- Replacing the local cache with a live read. Considered and rejected — see Decisions.
- Fixing the cloud-side over-revocation. That is `errand-cloud`'s `revoke-endpoints-only-on-access-loss`; this change assumes revocation can happen for *any* reason and recovers regardless.
- Continuous reconciliation. Connect-time only.
- Preserving endpoint tokens across re-registration. Not possible; the cloud mints a new token.
- Reconciling Slack, which already reconciles.

## Decisions

**Keep the local cache and reconcile, rather than reading `/api/endpoints` live.** A live read makes divergence structurally impossible and deletes a whole class of bug, which is its appeal. It also makes the panel go blank whenever the cloud is unreachable — including the "Cloud not connected" case the spec already handles deliberately — and turns a settings page render into a dependency on a remote service. The cache is worth keeping; what it lacked was a refresh path.

**Reconcile on connect, not on page load.** The settings page is not the only consumer of these URLs, and reconciliation that only runs when someone happens to open a settings tab is not reconciliation. Connect is when the cloud becomes reachable and when Slack already reconciles, so the two stay in step and share a trigger point.

**Check by token, re-register by trigger.** `GET /api/endpoints?integration=<x>` returns only non-revoked endpoints, so a stored token absent from that response is either revoked or gone — both mean "re-register". Re-registration goes through the existing `POST /api/endpoints` upsert keyed on `trigger_id`, reusing the trigger's stored webhook secret, so the cloud matches it to the same logical trigger.

**Reuse the existing secret; do not regenerate.** The secret is already configured in Jira or GitHub. Regenerating would break signature verification on the very deliveries reconciliation is meant to restore, converting a dead URL into a live URL that rejects everything — a worse failure, because it looks fixed.

**Clear `cloud_webhook_url` when re-registration fails.** Leaving the old URL displayed is what made this invisible. Clearing it surfaces the existing "Registration failed — re-save trigger to retry" row, which is already specified and already rendered. This is the part that matters even when reconciliation cannot help — no active subscription, cloud unreachable mid-pass — because it converts a silent failure into a visible one.

**Reconciliation failures must not break the connect path.** Same posture as registration today: log, continue. A cloud connect that fails because reconciliation errored would be a worse outcome than a stale URL.

## Risks / Trade-offs

- **The re-registered URL is new, and the user must update Jira or GitHub.** Reconciliation restores the endpoint but cannot repoint the third party at it. A silently-dead URL becomes a silently-dead-until-updated URL — better, but not self-healing end to end. Whether the user is told, and how, is an open question below.
- **Clearing `cloud_webhook_url` on failure discards the last-known URL.** If the cloud is merely having a bad minute, a working URL disappears from the page until the next successful pass. The alternative — keep displaying it — is the bug being fixed. Reconciliation must therefore distinguish "the cloud says this endpoint is gone" from "I could not reach the cloud", and only clear on the former.
- **A reconciliation bug could mass-re-register.** If the existence check misreads the response — an error body, an empty list from a failed call treated as "none exist" — every trigger re-registers and every URL changes at once. `check_existing_endpoints` currently returns `[]` on exception, which is exactly this hazard. The generalised helper must distinguish failure from emptiness, and this is the single most important detail in the change.
- **Connect-time only leaves a window.** An endpoint revoked mid-session stays stale until reconnect.
- **Extra requests per connect.** One listing call per integration with triggers. Negligible, and it replaces no existing call.

## Migration Plan

No schema change — `cloud_webhook_url` and `cloud_endpoint_token` already exist.

Existing stale triggers are repaired by the first reconciliation pass after deploy, on the next cloud connect. Triggers whose endpoints are genuinely gone get new URLs, which users must paste into Jira or GitHub. Nothing needs to be done by hand ahead of the deploy.

Deploy order does not matter. This change is independent of the errand-cloud fix: without it, reconciliation repairs endpoints that errand-cloud keeps wrongly revoking; with it, the wrongful revocation stops and reconciliation becomes the safety net rather than the cure.

## Open Questions

- **Should the user be told a URL changed?** A re-registered trigger silently gets a new URL and the old one stops working in the third party. A toast or a per-row marker may be warranted — but only for URLs that actually changed, or it becomes noise on every connect.
- **Should reconciliation extend to `cloud_endpoints` for Slack?** Slack already reconciles by a different mechanism. Folding both into the generalised helper would be tidier and is a small extra step, but it touches a working path.
- **Is connect-time enough?** If revocations prove common, a periodic pass or a cloud-pushed invalidation would close the mid-session window. Not worth building until the errand-cloud fix has landed and revocations are known to be rare.
