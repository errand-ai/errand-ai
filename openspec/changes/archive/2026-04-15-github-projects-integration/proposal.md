## Why

Errand's webhook integration currently supports Jira as the only source for automated task creation and lifecycle management. GitHub Projects V2 is widely used for issue tracking and project management, and teams using GitHub need the same automated workflow: when an issue is triaged and ready for implementation, errand should automatically create a task, implement the change using openspec, create a PR, and manage the issue's lifecycle on the project board. This extends errand's reach to GitHub-native teams without requiring Jira.

## What Changes

- Add a GitHub webhook handler that processes `projects_v2_item` events from GitHub Projects V2
- Implement a GitHub GraphQL + REST client for project board operations (column transitions, issue comments, PR creation, review requests)
- Extend the webhook receiver dispatch to route `github` source webhooks to the new handler
- Extend the external status updater to perform GitHub-specific actions on task status changes (column transitions, comments, Copilot review requests, review task creation)
- Add GitHub Projects-specific filter and action keys to webhook trigger validation
- Add a project introspection API endpoint that discovers project fields and column options via GraphQL
- Add frontend UI for configuring GitHub Projects webhook triggers (project URL, column mapping, review options)
- Add documentation for configuring GitHub webhooks and Projects V2 automation workflows

## Capabilities

### New Capabilities
- `github-webhook-handler`: Webhook payload parsing for GitHub `projects_v2_item` events, filter evaluation (project, column, content type), issue resolution via GraphQL, and task creation with ExternalTaskRef
- `github-graphql-client`: GraphQL and REST client for GitHub API operations — project introspection (fields, columns, items), column transitions, issue comments, PR creation, and review requests
- `github-project-trigger-config`: Webhook trigger configuration for GitHub Projects — project introspection endpoint, column mapping, review options (Copilot review, errand review task), and frontend settings UI
- `github-implementation-prompt`: System prompt template for GitHub Projects tasks — openspec change discovery, implementation, verification, branch creation, PR creation with structured JSON output

### Modified Capabilities
- `webhook-receiver`: Add dispatch routing for `source="github"` to the new GitHub webhook handler
- `external-status-updater`: Add GitHub-specific action handlers for column transitions, issue comments, Copilot review requests, and review task creation on task completion
- `webhook-trigger-model`: Add GitHub Projects-specific filter keys (`project_node_id`, `trigger_column`, `content_types`) and action keys (`column_on_running`, `column_on_complete`, `copilot_review`, `review_profile_id`)

## Impact

- **Backend**: New `platforms/github/` package (handler, client, queries), modifications to webhook receiver, external status updater, and webhook trigger routes
- **Frontend**: New GitHub Projects trigger configuration UI in webhook trigger settings
- **Database**: Alembic migration if webhook trigger model schema validation changes require it (likely no schema change — filters/actions are JSON fields)
- **Dependencies**: No new Python dependencies expected — `httpx` (already used) handles GraphQL requests
- **Infrastructure**: Requires org-level GitHub webhook configuration pointing to errand's `/webhooks/github` endpoint
- **Task Runner**: No changes — existing image already includes `git`, `gh`, `openspec`, and required runtimes
