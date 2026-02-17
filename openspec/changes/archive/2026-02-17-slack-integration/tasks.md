## 1. Dependencies and project setup

- [x] 1.1 Add `slack-sdk` to `backend/requirements.txt`
- [x] 1.2 Rebuild backend venv: `backend/.venv/bin/pip install -r backend/requirements.txt`
- [x] 1.3 Bump VERSION file (minor version bump — new feature)

## 2. Slack request signature verification

- [x] 2.1 Create `backend/platforms/slack/` package with `__init__.py`
- [x] 2.2 Create `backend/platforms/slack/verification.py` with `verify_slack_request` FastAPI dependency (HMAC-SHA256 signature check, timestamp replay protection)
- [x] 2.3 Write tests for signature verification (valid signature, invalid signature, missing headers, expired timestamp, no Slack credentials configured)

## 3. Slack user identity resolution

- [x] 3.1 Create `backend/platforms/slack/identity.py` with `resolve_slack_email(user_id)` function using Slack `users.info` API
- [x] 3.2 Implement in-memory cache with 1-hour TTL for user_id → email mappings
- [x] 3.3 Write tests for email resolution (cache hit, cache miss, no email available, cache expiry)

## 4. Slack slash command routing

- [x] 4.1 Create `backend/platforms/slack/routes.py` with FastAPI `APIRouter` mounted at `/slack`
- [x] 4.2 Implement `POST /slack/commands` endpoint with signature verification dependency
- [x] 4.3 Implement command parser: extract subcommand and arguments from Slack command text
- [x] 4.4 Implement dispatch logic: route to handler based on subcommand (new, status, list, run, output)
- [x] 4.5 Implement help/error response for unknown subcommands and empty commands
- [x] 4.6 Write tests for command parsing and dispatch (valid subcommands, unknown subcommand, empty command)

## 5. Slack Block Kit message builders

- [x] 5.1 Create `backend/platforms/slack/blocks.py` with Block Kit builder functions
- [x] 5.2 Implement `task_created_blocks(task)` — header, task fields, context line
- [x] 5.3 Implement `task_status_blocks(task)` — header, full task detail fields
- [x] 5.4 Implement `task_list_blocks(tasks)` — header, status-grouped task list with emoji, truncation
- [x] 5.5 Implement `task_output_blocks(task)` — header, code block with output, truncation handling
- [x] 5.6 Implement `error_blocks(message)` — warning emoji with error text
- [x] 5.7 Implement `help_blocks()` — available subcommands and usage
- [x] 5.8 Implement status emoji mapping function
- [x] 5.9 Write tests for all Block Kit builders (correct structure, truncation, empty states)

## 6. Slash command handlers

- [x] 6.1 Implement `/task new <title>` handler — create task, set created_by from Slack email, return created blocks
- [x] 6.2 Implement `/task status <id>` handler — lookup by UUID or prefix, return status blocks or error
- [x] 6.3 Implement `/task list [status]` handler — query tasks with optional status filter, return list blocks
- [x] 6.4 Implement `/task run <id>` handler — set status to pending, set updated_by, return confirmation
- [x] 6.5 Implement `/task output <id>` handler — return output blocks or status message
- [x] 6.6 Implement UUID prefix matching helper (query tasks where id starts with prefix, handle ambiguity)
- [x] 6.7 Write tests for each command handler (success, error, edge cases)

## 7. Slack Events API

- [x] 7.1 Implement `POST /slack/events` endpoint with URL verification challenge handling
- [x] 7.2 Write tests for URL verification (correct challenge response, non-verification events)

## 8. SlackPlatform class

- [x] 8.1 Create `SlackPlatform` class in `backend/platforms/slack/__init__.py` implementing `Platform` ABC
- [x] 8.2 Implement `info()` with capabilities `{COMMANDS, WEBHOOKS}` and credential_schema for `bot_token` and `signing_secret`
- [x] 8.3 Implement `verify_credentials()` making a test `auth.test` Slack API call
- [x] 8.4 Register `SlackPlatform` in the platform registry during application startup
- [x] 8.5 Write tests for SlackPlatform (info, verify_credentials)

## 9. FastAPI integration

- [x] 9.1 Mount Slack router on the main FastAPI app in `main.py`
- [x] 9.2 Ensure Slack routes do not conflict with existing routes (/api, /auth, /mcp)
- [x] 9.3 Write integration tests for the mounted Slack router (end-to-end command flow with mocked Slack verification)

## 10. Helm and deployment

- [x] 10.1 Add `/slack` path to ingress template (before catch-all `/` path), routing to backend service
- [x] 10.2 Verify ingress template renders correctly with all paths

## 11. Integration testing and validation

- [x] 11.1 Run full backend test suite and fix any failures
- [x] 11.2 Run full frontend test suite and fix any failures (no frontend changes expected, but verify nothing breaks)
- [x] 11.3 Test locally with `docker compose up --build` — verify Slack endpoints respond
- [x] 11.4 Document Slack app setup: required OAuth scopes, slash command URL configuration, signing secret location
