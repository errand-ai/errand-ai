## Why

Errand currently supports one inbound task trigger: email polling. To integrate with corporate project management tools like Jira and GitHub Projects, we need a webhook-based trigger system that receives push notifications when external items are created or updated, evaluates configurable filters, and creates tasks with the appropriate profile. This enables two-way integration: external tools delegate work to Errand via webhooks, and Errand feeds results back on task completion.

The immediate driver is Jira integration — allowing teams to label Jira tickets for automated execution and break down Feature tickets into sub-tasks via an LLM analyst. But the architecture must support future sources (GitHub Projects, Linear, etc.) without source-specific code in the core trigger engine.

## What Changes

- Add a **WebhookTrigger** model supporting multiple triggers per source, each with configurable filters (event types, issue types, labels, projects), actions (assign, comment, transition on completion), a task profile, and a webhook secret for HMAC verification
- Add an **ExternalTaskRef** model providing generic bidirectional reference tracking between errand tasks and external items (Jira issue keys, GitHub issue numbers, etc.) with source-specific metadata stored as JSON
- Add an **ExternalStatusUpdater** background service that subscribes to task events and dispatches completion callbacks (comments, status transitions) to external systems based on the trigger's configured actions — following the same Valkey pub/sub pattern as the Slack status updater
- Add **webhook receiver endpoints** (`POST /webhooks/{source}`) supporting both direct connections and cloud relay, with HMAC-SHA256 signature verification per trigger
- Add **Jira-specific handlers** as the first implementation: processing `issue_created` and `issue_updated` events, supporting configurable label and issue type filters, and calling the Jira REST API for assign/comment/transition actions
- Extend the **Task Generators settings UI** with a webhook triggers section allowing users to create, edit, and delete triggers with source selection, filter configuration, action toggles, profile assignment, and webhook secret management
- Add **Jira platform credential** support storing the service account API token (shared by both server-side API calls and the Atlassian MCP server in task profiles) in `PlatformCredential`
- Register **cloud endpoints** per webhook trigger, using the HMAC secret as a routing discriminator so errand-cloud can identify which errand instance should receive each webhook

## Capabilities

### New Capabilities

- `webhook-trigger-model`: WebhookTrigger database model, CRUD API endpoints, and filter/action configuration schema
- `external-task-ref`: ExternalTaskRef database model for generic bidirectional reference tracking between errand tasks and external system items
- `external-status-updater`: Background service subscribing to task events and dispatching completion callbacks to external systems based on trigger actions
- `webhook-receiver`: HTTP endpoints receiving webhooks from external sources (direct and cloud-relayed), with HMAC-SHA256 signature verification and fan-out to matching triggers
- `jira-webhook-handler`: Jira-specific webhook payload parsing, filter evaluation (event types, issue types, labels, projects), and task creation from Jira issue data
- `jira-completion-actions`: Server-side Jira REST API calls for completion callbacks — adding comments with task output, transitioning issue status, and assigning to service account
- `jira-platform-credential`: Jira service account credential storage, verification, and UI for configuring Jira Cloud connection (cloud ID, API token, site URL)
- `webhook-trigger-settings-ui`: Frontend settings interface for managing webhook triggers — CRUD operations, source selection, filter builders, action toggles, profile assignment, and secret management

### Modified Capabilities

- `cloud-webhook-dispatch`: Add routing for Jira (and generic webhook) integration types alongside existing Slack dispatch
- `cloud-endpoint-management`: Register per-trigger webhook endpoints with errand-cloud, including HMAC secrets for routing
- `task-generator-settings-ui`: Extend the Task Generators page to include webhook triggers section alongside the existing email trigger

## Impact

- **New files**: `errand/webhook_trigger_routes.py`, `errand/webhook_receiver.py`, `errand/external_status_updater.py`, `errand/platforms/jira/` (client, handlers, credential config)
- **Modified files**: `errand/models.py` (new models + migration), `errand/cloud_dispatch.py` (Jira routing), `errand/cloud_endpoints.py` (per-trigger registration), `errand/main.py` (lifespan: start status updater, mount webhook routes)
- **Frontend**: New components in `frontend/src/pages/settings/` for webhook trigger management, Jira credential setup
- **Database**: Alembic migration for `webhook_triggers` and `external_task_refs` tables
- **Dependencies**: No new Python dependencies — Jira REST API calls use existing `httpx`
- **MCP**: Atlassian MCP server configured per-profile via existing `mcp_servers` field on TaskProfile, sharing the same service account API token from PlatformCredential
