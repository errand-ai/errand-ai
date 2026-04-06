# GitHub Projects Integration

This guide covers configuring errand to automatically create and manage tasks from GitHub Projects V2 boards.

## Prerequisites

- A GitHub organization with Projects V2 enabled
- One of the following GitHub credential types:
  - **Classic PAT** with scopes: `repo`, `project`, `admin:org_hook`
  - **Fine-grained PAT** or **GitHub App** with these permissions:
    - Repository: `Issues` (read/write), `Pull requests` (read/write), `Contents` (read/write), `Metadata` (read)
    - Organization: `Projects` (read/write)
- Access to configure organization-level webhooks

## 1. Configure GitHub Credentials

1. Navigate to **Settings > Integrations** in errand
2. Under GitHub, select your auth mode:
   - **Personal Access Token**: Paste a classic PAT with the scopes above, or a fine-grained PAT with the listed permissions
   - **GitHub App**: Provide the App ID, private key (PEM), and installation ID
3. Click **Save** and verify the connection status shows "Connected"

## 2. Set Up GitHub Projects Workflow

Configure your GitHub Project board with the following recommended columns:

| Column | Purpose |
|--------|---------|
| Backlog | New issues waiting for triage |
| Ready | Issues with completed openspec artifacts, ready for implementation |
| In Progress | Issues being worked on by errand |
| In Review | PRs created, awaiting review |
| Done | Completed (auto-managed by GitHub Projects "item closed" workflow) |

### Recommended GitHub Projects Automations

In your Project settings, enable these built-in automations:
- **Item added to project** → Set status to "Backlog"
- **Item closed** → Set status to "Done"

The "Ready → In Progress → In Review" transitions are managed by errand.

## 3. Create an Organization Webhook

1. Go to your GitHub organization: **Settings > Webhooks > Add webhook**
2. Configure:
   - **Payload URL**: `https://your-errand-instance/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: Generate a secret (you'll use this in errand's trigger config)
   - **Events**: Select "Projects v2 items" only
3. Click **Add webhook**

The webhook fires for all projects in the organization. Errand filters by the specific project configured in each trigger.

## 4. Create an Errand Webhook Trigger

1. Navigate to **Settings > Webhook Triggers** in errand
2. Click **Add Trigger**
3. Select **Source: GitHub**
4. Configure:

### Project Introspection

Enter your org name and project number, then click **Introspect**. This discovers the project's Status field and column options, which populate the dropdowns below.

### Filters

- **Trigger Column**: The column that triggers task creation (typically "Ready")
- **Content Types**: What to process (default: Issues only)

### Actions

- **Column on Running**: Column to move issues to when errand starts (e.g., "In Progress")
- **Column on Complete**: Column to move issues to after PR creation (e.g., "In Review")
- **Add Comment**: Post comments on the issue for task lifecycle events
- **Copilot Review**: Automatically request GitHub Copilot review on created PRs
- **Review Task Profile**: Create a follow-up errand review task using this profile

### Task Prompt

Optional additional instructions appended to the system prompt for tasks created by this trigger.

### Webhook Secret

Paste the same secret you configured in the GitHub organization webhook.

5. Click **Save**

## 5. Workflow

Once configured, the end-to-end workflow is:

1. A team member creates openspec artifacts for an issue (proposal, design, specs, tasks)
2. When ready, they move the issue to the "Ready" column on the project board
3. GitHub sends a webhook to errand
4. Errand creates a task, moves the issue to "In Progress", and posts a comment
5. The task runner clones the repo, discovers the openspec change, implements it
6. A PR is created with `Relates to #N` linking to the issue
7. Errand moves the issue to "In Review" and optionally requests Copilot review
8. After review and merge, GitHub's built-in "item closed" automation moves to "Done"

## Structured Output

The task runner outputs a JSON block that errand parses for post-completion actions:

```json
{
  "status": "completed",
  "change_name": "fix-auth-redirect",
  "branch": "bug/fix-auth-redirect",
  "pr_number": 47,
  "pr_url": "https://github.com/org/repo/pull/47",
  "issue_number": 42,
  "summary": "Implemented fix for auth redirect loop"
}
```

If the task cannot proceed (e.g., no matching openspec change), it aborts:

```json
{
  "status": "aborted",
  "reason": "No openspec changes found in this repository",
  "issue_number": 42
}
```

## Troubleshooting

### Webhook not triggering
- Verify the webhook is active in GitHub org settings (check Recent Deliveries)
- Ensure the secret in errand matches the one in GitHub
- Check errand logs for signature verification failures

### Issue not creating a task
- Verify the trigger's project_node_id matches (visible in errand logs)
- Check the trigger column matches the column the issue moved TO
- Ensure content_types includes "Issue" (default)
- Check for duplicate prevention — an issue can only create one task per trigger

### Column transition failing
- Project columns may have been renamed since trigger creation
- Re-introspect the project to refresh cached column options
- Check errand logs for GraphQL errors
