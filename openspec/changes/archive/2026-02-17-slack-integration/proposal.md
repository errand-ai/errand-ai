## Why

With the platform abstraction in place (from platform-foundation), Slack can be added as the first interaction surface — a bidirectional interface where users create tasks, check status, and view outputs directly from Slack. This transforms Slack from a passive notification channel into an active UI for the system, complementing the web interface. Slack's slash commands and Block Kit provide a rich, mobile-friendly interaction model that requires no browser.

## What Changes

- Implement `SlackPlatform` class using the platform abstraction, with capabilities for commands and webhooks
- Add FastAPI routes for Slack webhook endpoints (`/slack/commands`, `/slack/events`) with HMAC-SHA256 request signature verification
- Implement slash command parsing and dispatch for task operations: `/task new`, `/task status`, `/task list`, `/task run`, `/task output`
- Build Block Kit message formatters for task responses (creation confirmations, status cards, task lists, output display)
- Resolve Slack user identity (user_id → email) via Slack API with caching, bridging to the Keycloak identity model via email matching
- Populate `created_by`/`updated_by` audit fields on tasks created or modified via Slack, using the resolved email address
- Add Slack webhook path (`/slack/*`) to the Helm ingress configuration
- Add Slack Events API URL verification handler (required for Slack app setup)

## Capabilities

### New Capabilities
- `slack-commands`: Slash command handling, dispatch, and response formatting for task operations via Slack
- `slack-webhook-security`: Request signature verification and Slack Events API URL verification
- `slack-user-identity`: Slack user-to-email resolution with caching, bridging Slack identity to the system's email-based user model

### Modified Capabilities
- `helm-deployment`: Ingress updated with `/slack/*` path routing to backend service

## Impact

- **Backend**: New `backend/platforms/slack/` package with routes, command handlers, Block Kit builders, signature verification, and user identity resolution. SlackPlatform registered in the platform registry.
- **Dependencies**: `slack-sdk` added to backend requirements (for Slack Web API calls and signature verification).
- **Helm**: Ingress template updated with `/slack/*` path.
- **Infrastructure**: Slack app must be created in the Slack API dashboard with slash commands configured to point at the deployment URL. Requires `commands`, `chat:write`, and `users:read.email` OAuth scopes.
- **Security**: All inbound Slack requests verified via HMAC-SHA256 signing secret. Slack user identity resolved to email and recorded in task audit fields.
