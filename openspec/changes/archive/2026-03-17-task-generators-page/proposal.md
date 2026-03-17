## Why

The email integration currently conflates IMAP/SMTP connection credentials with task-generation settings (task profile, poll interval) in a single form. This makes it impossible to add new trigger types (GitHub webhooks, generic webhooks) without creating more one-off forms. Extracting task-generation settings into a dedicated "Task Generators" page with a generic data model provides a clean home for all trigger types and prepares for the Google Workspace change, which will no longer need to touch the email poller.

## What Changes

- **Create `TaskGenerator` model and API**: New database table storing trigger configurations with `type` field (starting with `email`), `enabled` flag, `profile_id`, and type-specific `config` JSON. REST endpoints for listing and managing generators.
- **Create "Task Generators" settings page**: New route at `/settings/task-generators` with per-trigger-type cards. The email card contains enable/disable toggle, task profile selector, poll interval input, and a new task prompt textarea.
- **Add "Task Generators" link to settings sidebar**: Appears after "Integrations" in navigation order.
- **Refactor email poller**: Read task profile, poll interval, and task prompt from the `task_generator` record instead of email platform credentials. Respect the `enabled` flag.
- **Simplify email credential form**: Remove `email_profile` and `poll_interval` fields from the email credential schema. Keep only IMAP/SMTP connection settings and authorized recipients.
- **Data migration**: Move existing `email_profile` and `poll_interval` from email platform credentials to a new `task_generator` record with `type="email"`.

## Capabilities

### New Capabilities

- `task-generator-settings-ui`: Settings page at `/settings/task-generators` displaying trigger configurations as cards, starting with email trigger
- `task-generator-email`: Backend model, API, and data migration for task generator configurations

### Modified Capabilities

- `email-credential-ui`: Remove task profile selector and poll interval from email credential form; keep connection settings and authorized recipients only
- `email-poller`: Read task generation config (profile, poll interval, task prompt) from task_generator record instead of email credentials; respect enabled/disabled flag
- `settings-navigation`: Add "Task Generators" link to settings sidebar after Integrations

## Impact

- **Database**: New `task_generator` table + data migration from email credentials
- **Backend**: New `task_generator_routes.py` with API endpoints; `email_poller.py` config source changes; new model in `models.py`
- **Frontend**: New `TaskGeneratorsPage.vue` component; settings sidebar update; email credential form field removal
- **Existing users**: Email poller settings automatically migrated; no manual action needed
