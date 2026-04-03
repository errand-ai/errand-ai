## 1. Database Models & Migrations

- [x] 1.1 Add WebhookTrigger model to `errand/models.py` with fields: id (UUID), name (str, unique), enabled (bool, default false), source (str), profile_id (FK to TaskProfile, nullable), filters (JSON), actions (JSON), task_prompt (text, nullable), webhook_secret (text, nullable), created_at, updated_at
- [x] 1.2 Add ExternalTaskRef model to `errand/models.py` with fields: id (UUID), task_id (FK to Task, unique, cascade delete), trigger_id (FK to WebhookTrigger, nullable, set null on delete), source (str), external_id (str), external_url (str), parent_id (str, nullable), metadata (JSON), created_at, updated_at — with unique constraint on (external_id, source)
- [x] 1.3 Create Alembic migration for both tables with indexes on ExternalTaskRef(task_id), ExternalTaskRef(external_id, source), and WebhookTrigger(source, enabled)
- [x] 1.4 Write tests for model creation, relationships, cascade behaviors, and unique constraints

## 2. WebhookTrigger CRUD API

- [x] 2.1 Create `errand/webhook_trigger_routes.py` with endpoints: GET /api/webhook-triggers (list), GET /api/webhook-triggers/{id} (get), POST /api/webhook-triggers (create), PUT /api/webhook-triggers/{id} (update), DELETE /api/webhook-triggers/{id} (delete) — admin-only
- [x] 2.2 Implement filter schema validation: event_types (list of str), issue_types (list of str), labels (list of str), projects (list of str) — all optional, reject unknown keys
- [x] 2.3 Implement action schema validation: assign_to (str), add_comment (bool), add_label (str), transition_on_complete (str), comment_output (bool) — all optional, reject unknown keys
- [x] 2.4 Encrypt webhook_secret on save, never return in GET responses (return has_secret boolean instead)
- [x] 2.5 Mount routes in `errand/main.py`
- [x] 2.6 Write tests for all CRUD operations, validation, secret masking, and error cases

## 3. Jira Platform Credential

- [x] 3.1 Add Jira credential endpoints to `errand/integration_routes.py` or new file: PUT /api/credentials/jira (save with verification), GET /api/credentials/jira (status only, no token), DELETE /api/credentials/jira
- [x] 3.2 Implement credential verification: call GET /rest/api/3/myself via api.atlassian.com/ex/jira/{cloud_id}/ with Bearer token, store account display name on success
- [x] 3.3 Write tests for credential save/verify/delete flows, including verification failure handling

## 4. Webhook Receiver

- [x] 4.1 Create `errand/webhook_receiver.py` with POST /webhooks/{source} endpoint
- [x] 4.2 Implement HMAC-SHA256 signature verification: load enabled triggers for source, try each trigger's secret against the signature header, first match wins, 401 if no match
- [x] 4.3 Implement event deduplication with TTL cache (5 min) using webhook event ID from payload
- [x] 4.4 Implement async processing: return 200 immediately, dispatch to source handler as background task
- [x] 4.5 Add source-specific header extraction (Jira: X-Hub-Signature with sha256= prefix)
- [x] 4.6 Mount webhook routes in `errand/main.py`
- [x] 4.7 Write tests for HMAC verification (match, no match, no header), deduplication, and async dispatch

## 5. Cloud Integration

- [x] 5.1 Extend `errand/cloud_dispatch.py` to route `integration: "jira"` with `endpoint_type: "webhook"` to Jira handler, passing trigger_id from relay message
- [x] 5.2 Extend `errand/cloud_endpoints.py` to register/deregister per-trigger webhook endpoints with cloud on trigger create/update/delete
- [x] 5.3 Call cloud registration from webhook trigger CRUD routes when cloud is connected
- [x] 5.4 Write tests for cloud dispatch routing and endpoint registration lifecycle

## 6. Jira Webhook Handler

- [x] 6.1 Create `errand/platforms/jira/__init__.py` and `errand/platforms/jira/handler.py`
- [x] 6.2 Implement Jira payload parsing: extract webhookEvent, issue key, summary, description, issuetype, labels, project key, parent, reporter, priority
- [x] 6.3 Implement filter evaluation: event_types match against webhookEvent, issue_types match against issuetype.name, labels match against issue labels (with changelog check for label_added on updates), projects match against project.key
- [x] 6.4 Implement task creation on filter match: title from "{issue_key}: {summary}", description from issue description + metadata, profile from trigger, status "pending", tag "jira", created_by "jira:{issue_key}"
- [x] 6.5 Create ExternalTaskRef on task creation: source="jira", external_id=issue key, external_url from issue self link, parent_id from parent issue, metadata with project_key and cloud_id
- [x] 6.6 Implement deduplication: check ExternalTaskRef by (external_id, source) before creating task
- [x] 6.7 Write tests for payload parsing, each filter type, task creation, ref creation, and deduplication

## 7. Jira Completion Actions

- [x] 7.1 Create `errand/platforms/jira/client.py` with httpx-based Jira API client using Bearer token from PlatformCredential against api.atlassian.com gateway
- [x] 7.2 Implement add_comment: POST /rest/api/3/issue/{key}/comment with ADF body, truncate output to 30KB
- [x] 7.3 Implement transition_on_complete: GET transitions, find by name (case-insensitive), POST transition
- [x] 7.4 Implement assign_to: resolve account ID from service account email (cached), PUT assignee
- [x] 7.5 Implement add_label: PUT /rest/api/3/issue/{key} with updated labels array
- [x] 7.6 Implement error handling: log failures, store error in ExternalTaskRef metadata, skip remaining actions on 401
- [x] 7.7 Write tests for each action, error handling, and credential failure scenarios

## 8. External Status Updater

- [x] 8.1 Create `errand/external_status_updater.py` subscribing to Valkey "task_events" channel
- [x] 8.2 On task_updated event: look up ExternalTaskRef by task_id, load WebhookTrigger by trigger_id, dispatch by source
- [x] 8.3 Implement Jira dispatch: call appropriate actions from jira/client.py based on trigger actions config and status transition (running: optional comment+assign, completed: comment output+transition, failed: comment error)
- [x] 8.4 Handle missing trigger (deleted): skip callback, log info
- [x] 8.5 Start as background task in `errand/main.py` lifespan
- [x] 8.6 Write tests for event subscription, ref lookup, action dispatch, and error resilience

## 9. Frontend: Jira Credential Settings

- [x] 9.1 Create `JiraCredentialSettings.vue` component on the Integrations page: inputs for site URL, cloud ID, API token, service account email — with save/verify/disconnect actions
- [x] 9.2 Wire up to credential API endpoints (PUT/GET/DELETE /api/credentials/jira)
- [x] 9.3 Display verification status (connected/disconnected with account display name)
- [x] 9.4 Write frontend tests for credential form, save flow, and status display

## 10. Frontend: Webhook Trigger Settings

- [x] 10.1 Add "Webhook Triggers" section to TaskGeneratorsPage.vue showing list of configured triggers with name, source, enabled toggle, profile name
- [x] 10.2 Create trigger creation form: source selector, name input, enabled toggle, profile dropdown, task prompt textarea, webhook secret field (generate/paste, masked after save)
- [x] 10.3 Create Jira-specific filter configuration: event types multi-select, issue types multi-select, labels input (tag-style), projects input (tag-style)
- [x] 10.4 Create actions configuration: checkboxes for assign to service account, add comment with task reference, comment output on complete — text inputs for add label, transition on complete
- [x] 10.5 Create trigger edit form (populate from existing trigger, allow secret regeneration)
- [x] 10.6 Create trigger detail view showing webhook URL (direct URL or cloud relay URL based on cloud connection status)
- [x] 10.7 Add delete trigger confirmation dialog
- [x] 10.8 Wire up all forms to webhook trigger CRUD API
- [x] 10.9 Write frontend tests for trigger list, create, edit, delete, and filter/action configuration
