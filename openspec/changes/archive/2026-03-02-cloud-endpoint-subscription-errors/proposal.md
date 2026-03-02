## Why

When cloud endpoint registration fails due to a missing or expired subscription, the UI silently fails and leaves a permanent "Endpoints are being registered..." message with no way for the user to understand what went wrong. Users also have no visibility into their subscription status or expiry date, making it impossible to self-diagnose or act on subscription issues.

## What Changes

- The backend checks subscription status from the cloud service and exposes it via `GET /api/cloud/status`
- The cloud settings page displays the subscription expiry date when connected
- If the subscription is expired or missing, a toast notification is shown immediately (no silent failure)
- The "Endpoints are being registered..." message is replaced by an error state when registration fails
- Subscription status is checked proactively on page load so expired subscriptions surface without requiring a registration attempt

## Capabilities

### New Capabilities
- `cloud-subscription-status`: Backend fetches and exposes subscription status (active/expired, expiry date) from the cloud service; frontend displays it on the Cloud Service settings page

### Modified Capabilities
- `cloud-endpoint-management`: Registration failures (including "Active subscription required" 403) SHALL surface to the user via a toast notification and SHALL NOT leave the UI in a perpetual "registering" state
- `cloud-settings-ui`: Connected state SHALL display subscription expiry date; SHALL show an error message and toast when subscription is missing or expired rather than a loading indicator

## Impact

- **Backend**: `GET /api/cloud/status` response gains `subscription` object; new call to cloud service subscription API; `cloud_endpoints.py` registration failure propagated to frontend via `cloud_status` SSE event
- **Frontend**: `CloudServicePage.vue` updated to render subscription info and handle endpoint registration errors; no new dependencies
- **Specs**: `cloud-endpoint-management` and `cloud-settings-ui` get delta specs; new `cloud-subscription-status` spec
