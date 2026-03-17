## 1. Backend — TaskGenerator Model and API

- [x] 1.1 Create `TaskGenerator` SQLAlchemy model in `models.py` (id UUID PK, type text unique, enabled bool default false, profile_id UUID FK nullable, config JSON, created_at, updated_at)
- [x] 1.2 Create Alembic migration: create `task_generator` table and migrate existing `email_profile`/`poll_interval` from email platform credentials to a task_generator record with `type="email"` and `enabled=true`
- [x] 1.3 Create `task_generator_routes.py` with endpoints: `GET /api/task-generators`, `GET /api/task-generators/email`, `PUT /api/task-generators/email` (upsert)
- [x] 1.4 Register task generator API routes in `main.py`

## 2. Backend — Email Poller Refactor

- [x] 2.1 Update email poller to read task generation config (profile_id, poll_interval, task_prompt) from `task_generator` record with `type="email"` instead of email platform credentials
- [x] 2.2 Add enabled/disabled check: poller sleeps when email task generator is missing or disabled
- [x] 2.3 Append task prompt to task description when creating tasks from email (with delimiter)
- [x] 2.4 Remove `email_profile` and `poll_interval` reads from email platform credential in poller

## 3. Frontend — Task Generators Page

- [x] 3.1 Create `TaskGeneratorsPage.vue` component at route `/settings/task-generators`
- [x] 3.2 Add "Task Generators" link to settings sidebar navigation (after Integrations)
- [x] 3.3 Build email trigger card: enable/disable toggle, task profile selector dropdown, poll interval input, task prompt textarea
- [x] 3.4 Wire up API calls to `GET/PUT /api/task-generators/email`
- [x] 3.5 Add validation: poll interval minimum 60 seconds, show message when email credentials not configured

## 4. Frontend — Email Credential Simplification

- [x] 4.1 Remove `email_profile` (profile_select) and `poll_interval` fields from email platform credential schema/form
- [x] 4.2 Verify authorized_recipients field remains in email credential form

## 5. Tests

- [x] 5.1 Add backend tests for TaskGenerator model and API endpoints (CRUD, upsert, migration)
- [x] 5.2 Add backend tests for email poller reading config from task generator (enabled/disabled, profile, poll interval, task prompt)
- [x] 5.3 Add frontend tests for TaskGeneratorsPage component (email card rendering, toggle, validation, API calls)
- [x] 5.4 Update existing email credential frontend tests to reflect removed fields

## 6. Documentation and VERSION

- [x] 6.1 Bump VERSION file (minor version — new feature)
- [x] 6.2 Update CLAUDE.md if needed: document Task Generators settings page
