## Context

Errand currently has one inbound task trigger: the email poller, which runs as a background asyncio task, polls IMAP for new messages, and creates tasks via `create_task_from_email()`. The Slack integration receives webhooks (both direct and cloud-relayed) and creates tasks from mentions and slash commands, with a `SlackStatusUpdater` that subscribes to task events and updates Slack messages as tasks progress.

The webhook trigger system extends both patterns: it receives push notifications from external project management tools (starting with Jira), creates tasks via configurable triggers, and feeds back completion status — but generalized beyond any single source.

Key existing infrastructure:
- `TaskGenerator` model with `type`/`enabled`/`profile_id`/`config` (currently only `type="email"`)
- `PlatformCredential` for encrypted credential storage
- `cloud_dispatch.py` routing by `integration` + `endpoint_type`
- `cloud_endpoints.py` registering per-integration endpoints with errand-cloud
- `SlackStatusUpdater` subscribing to Valkey `task_events` pub/sub
- `SlackMessageRef` tracking task ↔ Slack message references

## Goals / Non-Goals

**Goals:**

- Support multiple webhook triggers per source, each with independent filters, actions, profile, and webhook secret
- Provide generic reference tracking between errand tasks and external items (Jira issues, GitHub project items, etc.)
- Dispatch completion callbacks to external systems following the same pub/sub pattern as the Slack status updater
- Support both direct webhook connections and cloud relay with HMAC-based routing
- Enable Jira as the first webhook source: receive webhooks, create tasks, assign tickets, comment references, transition on completion
- Share a single Jira service account identity across server-side API calls and MCP tool access in task profiles

**Non-Goals:**

- Building a native Jira API client library — use `httpx` directly for the small number of REST calls needed
- GitHub Projects integration (future change — but the data model must accommodate it)
- Replacing the existing Slack integration with the webhook trigger system (Slack has its own patterns: slash commands, Block Kit, etc.)
- Two-way sync (keeping errand task descriptions in sync with Jira ticket updates after creation)
- Jira Server/Data Center support (Jira Cloud only for initial implementation)

## Decisions

### Decision 1: New `WebhookTrigger` table, not extending `TaskGenerator`

The `TaskGenerator` model has a unique constraint on `type` — one generator per type. Webhook triggers need N triggers per source (e.g., two Jira triggers with different filters). Rather than breaking the `TaskGenerator` contract, we add a new `WebhookTrigger` model.

**Why not evolve TaskGenerator?** The webhook trigger has significantly richer config (filters, actions, webhook secret, source-specific settings) that doesn't map to `TaskGenerator`'s simple `config` dict. The email poller is a pull-based singleton; webhook triggers are push-based with multiplicity. Separate models keep both simple.

**Alternative considered:** Drop the unique constraint on `TaskGenerator.type`, add `name` and `filters` columns. Rejected because it would complicate the email trigger's upsert semantics and conflate fundamentally different trigger mechanisms.

### Decision 2: `ExternalTaskRef` with source-specific `metadata` dict

Store a generic reference with human-readable fields (`external_id`, `external_url`, `parent_id`) and a JSON `metadata` column for source-specific IDs needed for API calls.

**Why not source-specific tables (JiraTaskRef, GitHubTaskRef)?** The completion callback dispatcher needs a uniform lookup: "given a task, find its external reference." A single table with source-discriminated metadata is simpler than polymorphic queries across N tables. The `metadata` dict is opaque to the generic layer — only source-specific handlers read it.

**Jira metadata:** `{ "project_key": "PROJ", "cloud_id": "abc-123" }`
**GitHub metadata (future):** `{ "owner": "org", "repo": "repo", "issue_number": 42, "item_node_id": "PVTI_...", "project_node_id": "PVT_..." }`

### Decision 3: HMAC secret on each WebhookTrigger, verified by trying all secrets for the source

Each webhook trigger stores its own `webhook_secret` (encrypted). When a webhook arrives at `POST /webhooks/{source}`:
1. Load all enabled triggers for that source
2. For each trigger with a secret, compute HMAC-SHA256 and compare to the `X-Hub-Signature` header
3. First match identifies the trigger — skip filter evaluation
4. If no secret matches, reject with 401

**Why not a shared secret per source?** Users may create multiple Jira webhook registrations (e.g., per project) with different secrets. Per-trigger secrets give full flexibility. The secret also doubles as a routing key in errand-cloud.

**Performance:** N HMAC computations per webhook is acceptable — expect < 10 triggers per source. Short-circuit on first match.

### Decision 4: ExternalStatusUpdater following SlackStatusUpdater pattern

A new background service subscribing to the same Valkey `task_events` channel. On `task_updated` events, it looks up `ExternalTaskRef` by `task_id`, loads the trigger's action config, and dispatches source-specific callbacks.

**Why not extend SlackStatusUpdater?** The Slack updater has Slack-specific logic (Block Kit formatting, message_ts semantics). A separate updater for external triggers keeps concerns clean. Both subscribe to the same channel — Valkey pub/sub supports multiple subscribers.

**Callback actions per status transition:**
- `pending → running`: Optional comment ("Task started"), optional assign to service account
- `running → completed`: Comment with output (truncated to Jira's 32KB limit), transition to configured status
- `running → failed`: Comment with error summary, optional label ("errand-failed")

### Decision 5: Jira REST API via `httpx`, Atlassian MCP via task profile

Server-side actions (assign, comment, transition) use direct Jira REST API calls via `httpx` against the `api.atlassian.com` gateway. The analyst use case (LLM reading and creating Jira issues) uses the Atlassian MCP server configured in the task profile's `mcp_servers`.

Both use the same Bearer token from `PlatformCredential(platform_id="jira")`. The MCP server config in the task profile references the credential: `{ "url": "https://mcp.atlassian.com/v1/mcp", "headers": { "Authorization": "Bearer ${jira_api_token}" } }`.

**Credential format:** `{ "cloud_id": "...", "api_token": "...", "site_url": "https://company.atlassian.net", "service_account_email": "errand-bot@company.com" }`

**Why scoped API token?** Jira Cloud service accounts support scoped tokens with up to 365-day expiry. Scoped tokens only work against the `api.atlassian.com/ex/jira/{cloud_id}/` gateway (not the site URL). The same Bearer token authenticates against the Atlassian MCP server.

### Decision 6: Cloud endpoint registration per trigger

Each webhook trigger registers its own endpoint with errand-cloud, including the HMAC secret. Cloud uses the secret to route webhooks to the correct errand instance (try HMAC against all registered secrets, first match wins). The relay message includes the matched `trigger_id` so errand can route directly.

Registration happens on trigger create/update/delete via `cloud_endpoints.py` (extending the existing pattern). A new endpoint type `"webhook"` is used alongside Slack's `"events"/"commands"/"interactivity"`.

### Decision 7: Webhook receiver supports direct and cloud paths

- **Direct**: `POST /webhooks/jira` receives the raw Jira payload with `X-Hub-Signature` header. Verifies HMAC locally, fans out to matching triggers.
- **Cloud relay**: `cloud_dispatch.py` receives relay message with `integration: "jira"`, `trigger_id: "..."`. Loads the specific trigger, re-verifies HMAC for defense in depth, processes.

Both paths converge at the same handler function, differing only in how the trigger is identified (HMAC match vs relay `trigger_id`).

## Risks / Trade-offs

**[Risk] HMAC verification with N secrets is O(N)** → Short-circuit on first match. Expected N < 10 per source. If this becomes a bottleneck, add a prefix-based index (first 8 chars of HMAC as lookup key).

**[Risk] Jira API token expires (max 365 days)** → Store `token_expires_at` in credential metadata. Add a warning in the UI when within 30 days of expiry. Token rotation requires updating both the credential and re-registering cloud endpoints.

**[Risk] Completion callback fails (Jira API down)** → Log the error, do not retry automatically (task is already completed in errand). Store the failure in `ExternalTaskRef.metadata` for manual retry. The task's completion status in errand is authoritative.

**[Risk] Duplicate webhook delivery** → Jira may retry failed deliveries (up to 5 times). Use the webhook event ID from the payload as a deduplication key with a 5-minute TTL cache (same pattern as Slack).

**[Risk] Webhook trigger filters become complex** → Start with simple field matching (event type, issue type, label, project). JSONPath-based custom filters are a future enhancement, not in initial scope.

**[Trade-off] Separate WebhookTrigger and TaskGenerator tables** → Two places for trigger configuration, but cleaner separation of pull (email) vs push (webhook) patterns. The settings UI groups them on the same page.

**[Trade-off] ExternalTaskRef metadata is untyped JSON** → Flexibility over type safety. Each source handler validates its own metadata shape. If this causes bugs, introduce pydantic models per source.
