## Context

Errand currently supports Jira as a webhook source for automated task creation and lifecycle management. The architecture follows a clean pattern: `webhook_receiver.py` validates and dispatches, a source-specific handler parses and creates tasks, and `external_status_updater.py` reacts to task status changes by calling back to the external service.

GitHub Projects V2 is a fundamentally different integration surface than Jira:
- Project board operations require the **GraphQL API** (not REST)
- `projects_v2_item` webhooks are **organization-level only** (not repo-level)
- Webhook payloads require **follow-up GraphQL calls** to resolve issue details from node IDs
- A single project spans **multiple repositories**, so one trigger handles issues from any repo in the project

The existing `platforms/github.py` provides credential management (PAT and GitHub App modes) but no webhook handling or API client.

## Goals / Non-Goals

**Goals:**
- Process GitHub Projects V2 `projects_v2_item` webhooks to create errand tasks when issues move to a configured "Ready" column
- Manage issue lifecycle on the project board (column transitions for In Progress, In Review)
- Create PRs with structured output that links back to the originating issue
- Support optional post-completion review workflows (Copilot review, errand review task)
- Provide a configuration UI for GitHub Projects triggers with project introspection

**Non-Goals:**
- Handling GitHub webhooks beyond `projects_v2_item` (e.g., `issues`, `pull_request` events) — future enhancement
- Managing the "Done" column transition — handled by GitHub Projects built-in workflows (item closed → Done)
- Defining the code review task profile — that's a separate concern; this integration only creates the review task
- Supporting user-owned projects — `projects_v2_item` webhooks are only available at the organization level
- Per-repository container image overrides — the existing task runner image includes Python, Node, git, gh, and openspec
- Creating or managing the GitHub Projects board itself — users configure the project and its workflows in GitHub

## Decisions

### Decision 1: GraphQL client using httpx

**Choice:** Implement the GitHub GraphQL client using `httpx` (already a project dependency) with raw GraphQL query strings.

**Alternatives considered:**
- `gql` library: Adds a dependency for schema validation and typed queries. Overkill for the ~10 queries/mutations needed.
- `sgqlc`: Code-generates typed client from schema. Heavy setup for limited benefit.

**Rationale:** The integration needs a small, fixed set of queries. Raw strings in a `queries.py` constants file are readable, testable, and add no dependencies. The client class wraps httpx with auth header injection and error handling.

### Decision 2: Cache project structure at trigger creation time

**Choice:** When a GitHub Projects trigger is created or updated, introspect the project via GraphQL to discover the Status field ID and all option IDs (Backlog, Ready, In Progress, etc.). Store these in the trigger's `filters` dict as `project_field_id` and `column_options` (a name→ID mapping).

**Alternatives considered:**
- Query on every webhook: Adds latency and API calls per event. Field/option IDs are stable.
- Manual configuration: User copies node IDs from GitHub — error-prone and poor UX.

**Rationale:** Project structure rarely changes. Caching at config time eliminates per-webhook overhead. A "refresh" action on the trigger config UI re-introspects if columns are renamed. The introspection endpoint also validates that the configured project URL is accessible with the stored GitHub credentials.

### Decision 3: Per-project triggers (not per-repo)

**Choice:** One webhook trigger covers an entire GitHub Project, which may contain issues from multiple repositories. The handler resolves the specific repo from the webhook payload via GraphQL.

**Alternatives considered:**
- Per-repo triggers: Would require N triggers for N repos in a project, all listening to the same org webhook. Redundant configuration.

**Rationale:** GitHub Projects inherently span repos. The org-level webhook delivers events for all projects, and the handler filters by `project_node_id`. Repo-specific details (clone URL, branch prefix) are derived from the issue metadata at processing time.

### Decision 4: Structured JSON task output contract

**Choice:** The system prompt for GitHub Projects tasks enforces a structured JSON output block as the final message. The `external_status_updater` parses this to extract the PR URL, branch name, and summary for post-completion actions.

**Format:**
```json
{
  "status": "completed",
  "change_name": "fix-auth-redirect",
  "branch": "bug/fix-auth-redirect",
  "pr_number": 47,
  "pr_url": "https://github.com/org/repo/pull/47",
  "issue_number": 42,
  "summary": "Implemented fix for auth redirect loop by..."
}
```

For abort cases:
```json
{
  "status": "aborted",
  "reason": "No matching openspec change found for this issue",
  "issue_number": 42
}
```

**Rationale:** The external status updater needs the PR reference to request reviews and post comments. A structured contract is more reliable than parsing free-text output. The task runner already captures stdout as task output, and the updater can extract fenced JSON blocks.

### Decision 5: Column transitions via external_status_updater actions

**Choice:** Extend the existing `external_status_updater` pattern with GitHub-specific action keys: `column_on_running`, `column_on_complete`, `copilot_review`, and `review_profile_id`. The updater calls the GitHub GraphQL client to perform column transitions and review actions.

**Alternatives considered:**
- Handle in the webhook handler: Conflates ingestion with lifecycle management. Breaks the existing separation of concerns.
- Webhook chain (PR creation triggers review via separate trigger): Elegant reuse but doubles configuration complexity and adds latency.

**Rationale:** The Jira pattern already works well — handler creates the task, updater manages the lifecycle. The GitHub updater follows the same dispatch pattern, just with different API calls (GraphQL mutations instead of Jira REST).

### Decision 6: Branch naming from issue labels

**Choice:** The system prompt derives the branch prefix from the issue's labels:
- `bug` label → `bug/<change-name>`
- `enhancement` label → `feature/<change-name>`
- Neither → `patch/<change-name>`

**Rationale:** The issue labels that triggered the project workflow (bug/enhancement) are already present. This gives meaningful branch prefixes without additional configuration.

### Decision 7: PR links to issue via "Relates to" (not "Closes")

**Choice:** The PR body uses `Relates to #N` instead of `Closes #N`.

**Rationale:** `Closes #N` auto-closes the issue on merge, which would bypass errand's board state management. Using `Relates to` keeps the issue open so that the review phase (In Review column) and final state transitions are managed explicitly by errand or GitHub Projects workflows.

### Decision 8: Openspec change discovery by scanning the repo

**Choice:** The task runner clones the repo, runs `openspec list --json`, and attempts to match a change to the issue. If exactly one in-progress change exists, use it. If multiple exist, attempt to match by reading proposals for issue references. If no match or ambiguous, abort with a comment on the issue.

**Alternatives considered:**
- Convention-based naming (change name = issue number): Too rigid, doesn't match natural naming.
- Issue field/label with change name: Adds manual overhead to the human workflow.

**Rationale:** The "Ready" column signal means artifacts exist and are complete. The LLM can read proposals and match contextually. The abort-with-comment fallback ensures no silent failures — the human gets a clear action item.

## Risks / Trade-offs

**[Org-level webhook noise]** → The org webhook delivers events for ALL projects. Errand filters by `project_node_id`, but high-activity orgs will send many irrelevant events. Mitigation: Fast filter-and-discard in the handler (check project ID before any GraphQL calls).

**[GraphQL API rate limits]** → Each webhook processing requires 1-2 GraphQL calls (resolve issue, find project item). GitHub's rate limit is 5,000 points/hour for apps. Mitigation: The project structure is cached, and individual issue resolution queries are cheap (~1 point each). Only triggers real work for "Ready" column moves.

**[Openspec change discovery is heuristic]** → If multiple changes exist, the LLM must match by reading proposals. This could fail for ambiguous cases. Mitigation: The prompt enforces strict abort-with-comment behavior. No guessing — if unclear, ask the human.

**[Stale project config cache]** → If project columns are renamed after trigger creation, the cached option IDs become invalid. Mitigation: The trigger config UI provides a "refresh" action. Column transition failures are logged and surfaced as task comments.

**[Review task creation couples two tasks]** → The implementation task's completion triggers review task creation via the updater. If the updater fails, the review task is never created. Mitigation: Log the failure and post a comment on the issue explaining that review task creation failed.

## Migration Plan

No database migration required — the `WebhookTrigger` model's `filters` and `actions` are JSON fields that already accept arbitrary keys. The new GitHub-specific keys are validated at the API level (webhook_trigger_routes.py) rather than the schema level.

Deployment is additive:
1. Deploy the backend changes (handler, client, updater extensions)
2. Deploy the frontend changes (trigger config UI)
3. Users configure GitHub credentials, create a trigger, and set up the org webhook
4. No changes to existing Jira triggers or behavior
