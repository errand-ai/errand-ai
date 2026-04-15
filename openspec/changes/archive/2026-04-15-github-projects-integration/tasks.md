## 1. GitHub Platform Package Restructure

- [x] 1.1 Convert `errand/platforms/github.py` to a package: create `errand/platforms/github/` directory with `__init__.py`, move existing credential/platform code to `errand/platforms/github/platform.py`, and update all imports
- [x] 1.2 Create `errand/platforms/github/queries.py` with GraphQL query and mutation string constants: project introspection query, issue resolution query, project item lookup query, update item field value mutation, and add comment mutation
- [x] 1.3 Add tests for the package restructure — verify platform registration, credential verification, and existing imports still work

## 2. GitHub GraphQL Client

- [x] 2.1 Create `errand/platforms/github/client.py` with `GitHubClient` class — constructor accepts credentials dict, initializes httpx async client with auth headers, implements `_graphql()` method for authenticated GraphQL requests with error extraction
- [x] 2.2 Implement `introspect_project(org, project_number)` method — queries project node ID, title, and all fields with SingleSelectField options (Status field discovery)
- [x] 2.3 Implement `resolve_issue(node_id)` method — resolves issue node ID to full details (number, title, body, url, repo owner/name, labels, assignees)
- [x] 2.4 Implement `find_project_item(issue_node_id, project_node_id)` method — finds ProjectV2Item ID and current Status for an issue within a project
- [x] 2.5 Implement `update_item_status(project_id, item_id, field_id, option_id)` method — executes updateProjectV2ItemFieldValue mutation
- [x] 2.6 Implement `add_comment(subject_id, body)` method — executes addComment mutation, returns comment URL
- [x] 2.7 Implement `request_review(owner, repo, pull_number, reviewers)` method — calls REST API POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers
- [x] 2.8 Add unit tests for GitHubClient — mock httpx responses for each method, test error handling for GraphQL errors, auth failures, and network errors

## 3. GitHub Webhook Handler

- [x] 3.1 Create `errand/platforms/github/handler.py` with `handle_github_webhook(payload, trigger, db)` function — parse payload, evaluate filters, resolve issue, create task
- [x] 3.2 Implement payload parsing — extract action, project_node_id, content_node_id, content_type, field_value changes (field_name, from.name, to.name)
- [x] 3.3 Implement filter evaluation — check project_node_id match, trigger_column match (case-insensitive), content_types match, action=="edited" and field_name=="Status"
- [x] 3.4 Implement issue resolution — call GitHubClient.resolve_issue() with content_node_id, handle DraftIssue rejection
- [x] 3.5 Implement task creation — create Task with title "{owner}/{repo}#{number}: {title}", description with issue metadata and task_prompt, ExternalTaskRef with GitHub-specific metadata (project_node_id, item_node_id, content_node_id, repo_owner, repo_name, issue_labels), tag with "github"
- [x] 3.6 Implement duplicate prevention — check ExternalTaskRef for existing task with same external_id and trigger_id
- [x] 3.7 Implement post-creation comment — call GitHubClient.add_comment() on the issue with task ID and link
- [x] 3.8 Add unit tests for handler — test payload parsing, each filter condition (pass/fail), task creation, deduplication, and comment posting with mocked GitHubClient

## 4. Webhook Receiver Dispatch

- [x] 4.1 Update `errand/webhook_receiver.py` `_dispatch_webhook()` to import and call `handle_github_webhook` when `trigger.source == "github"`
- [x] 4.2 Add test for GitHub webhook dispatch — verify the handler is called with correct arguments when source is "github"

## 5. External Status Updater — GitHub Actions

- [x] 5.1 Add GitHub status callback dispatch in `errand/external_status_updater.py` — when ExternalTaskRef source is "github", route to GitHub-specific action handlers
- [x] 5.2 Implement running actions — column transition (column_on_running) via GitHubClient.update_item_status() and comment (add_comment) via GitHubClient.add_comment()
- [x] 5.3 Implement structured output parsing — extract fenced JSON block from task output, parse into dict, handle missing/malformed output gracefully
- [x] 5.4 Implement completed actions — post summary comment (comment_output), request Copilot review (copilot_review + pr_number from output), create review task (review_profile_id + pr_url/branch from output), column transition (column_on_complete)
- [x] 5.5 Implement review task creation — create Task with review profile_id, description with PR URL and branch, ExternalTaskRef linking to same issue
- [x] 5.6 Implement failed actions — post failure comment on issue
- [x] 5.7 Implement aborted output handling — when structured output has status "aborted", post reason as comment, skip review and column actions
- [x] 5.8 Add unit tests for GitHub status updater — test each action (column transition, comment, Copilot review, review task creation), test aborted handling, test missing output handling

## 6. Webhook Trigger Validation — GitHub Filters and Actions

- [x] 6.1 Update `errand/webhook_trigger_routes.py` to add GitHub-specific filter validation — require `project_node_id` and `trigger_column`, validate `content_types` values
- [x] 6.2 Update `errand/webhook_trigger_routes.py` to add GitHub-specific action validation — validate `column_on_running`, `column_on_complete`, `copilot_review`, `review_profile_id` (check profile exists), `project_field_id`, `column_options`
- [x] 6.3 Add project introspection endpoint `POST /api/webhook-triggers/github/introspect-project` — accepts org + project_number, returns project node ID, title, status field ID, and column options
- [x] 6.4 Implement cached column options — when creating/updating a GitHub trigger with column actions but no column_options, auto-introspect the project and cache field_id + column_options in the trigger's actions
- [x] 6.5 Add tests for GitHub trigger validation — test required filter keys, invalid action keys, profile existence check, column name validation against cached options

## 7. System Prompt Template

- [x] 7.1 Create the system prompt template constant in `errand/platforms/github/prompt.py` — parameterized template covering all four phases (discovery, implementation, verification, delivery) with structured JSON output instructions
- [x] 7.2 Implement template rendering function that accepts issue metadata (number, title, repo, labels, url, task_id) and returns the complete system prompt
- [x] 7.3 Update the GitHub webhook handler to use the rendered system prompt as the task description (incorporating trigger's task_prompt as additional instructions)
- [x] 7.4 Add tests for prompt rendering — verify all parameters are substituted, branch prefix logic (bug/feature/patch), and task_prompt appending

## 8. Frontend — GitHub Projects Trigger Configuration

- [x] 8.1 Add GitHub source option to the webhook trigger form — show GitHub-specific fields when source="github" is selected
- [x] 8.2 Implement project introspection UI — org name and project number inputs with "Introspect" button, loading state, error display
- [x] 8.3 Implement column mapping dropdowns — populate from introspected Status field options, selectors for trigger column, column_on_running, column_on_complete
- [x] 8.4 Implement review options UI — Copilot review toggle, errand review task profile selector (populated from task profiles API), conditionally shown
- [x] 8.5 Wire form submission to create/update trigger with GitHub-specific filters and actions
- [x] 8.6 Add frontend tests for the GitHub trigger configuration component

## 9. Documentation

- [x] 9.1 Create GitHub Projects integration setup guide — document GitHub Projects workflow configuration (auto-add, item-added-to-project automation), org webhook creation, webhook secret setup, and required GitHub App/PAT permissions
- [x] 9.2 Document the errand trigger configuration workflow — how to create a GitHub Projects trigger, introspect a project, map columns, configure review options
