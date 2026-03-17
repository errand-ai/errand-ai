## Context

The Settings UI currently embeds email task-generation settings (task profile, poll interval) inside the email platform credential form. The email poller reads these values from the credential record. This coupling makes it difficult to add new trigger types and conflates connection settings with task-generation configuration.

This change extracts task-generation settings into a dedicated model, API, and settings page. It is a prerequisite for the Google Workspace CLI change, which will add further trigger types.

## Goals / Non-Goals

**Goals:**

- Introduce a `TaskGenerator` model that generalizes trigger configuration with a `type` discriminator
- Create a Task Generators settings page with per-trigger-type cards
- Migrate existing email task-generation settings out of platform credentials
- Add a "Task Prompt" field for email-triggered tasks
- Refactor the email poller to read from the new model

**Non-Goals:**

- Adding non-email trigger types (GitHub webhooks, generic webhooks — future changes)
- Changing IMAP/SMTP connection logic or authorized recipients handling
- Modifying the task creation pipeline beyond adding the task prompt field

## Decisions

### D1: Generic TaskGenerator model with type discriminator

A single `task_generator` table with a `type` text field and a `config` JSON column for type-specific settings. This avoids creating a new table for each trigger type while keeping the schema simple.

**Fields:** `id` (UUID PK), `type` (text, unique — one generator per type), `enabled` (boolean, default false), `profile_id` (UUID FK to task profiles, nullable), `config` (JSON), `created_at`, `updated_at`.

**Email config schema:** `{"poll_interval": int, "task_prompt": string|null}`

**Alternative considered:** Separate `email_task_config` table. Rejected because the generic model is equally simple and avoids a migration when adding webhook triggers later.

### D2: Upsert API pattern

`PUT /api/task-generators/email` creates or updates the email generator record (upsert). This matches the pattern used by other settings endpoints (e.g., platform credentials) and avoids the client needing to distinguish between create and update.

`GET /api/task-generators` returns all generators. `GET /api/task-generators/email` returns the email generator or 404.

### D3: Data migration — two-phase Alembic migration

A single Alembic migration that:
1. Creates the `task_generator` table
2. Reads existing email platform credentials with `email_profile` and `poll_interval` in their data JSON
3. Creates a `task_generator` record with `type="email"`, migrated values, and `enabled=true` (preserving current behavior)
4. Removes `email_profile` and `poll_interval` from the credential's data JSON

This is done in a single migration to avoid a window where the poller looks in the wrong place.

### D4: Email poller reads from TaskGenerator at each cycle

Rather than caching the task generator config, the poller queries the `task_generator` table on each poll cycle. This ensures config changes (enable/disable, profile change, poll interval) take effect without restarting the server.

The poller's startup logic becomes:
1. Check for email platform credentials (IMAP connection details) — sleep if missing
2. Check for enabled email task generator — sleep if missing or disabled
3. Read poll interval and task prompt from the generator's config
4. Poll/IDLE as before

### D5: Task prompt appended to task description

When the email task generator has a non-empty `task_prompt`, it is appended to the task description after the email content, separated by a clear delimiter (e.g., `\n\n---\n\n**Additional Instructions:**\n\n`). This keeps the email content intact while providing the LLM with supplementary guidance.

### D6: profile_select component stays in frontend

The `profile_select` field type is removed from the email credential schema but the component implementation remains in `PlatformCredentialForm.vue`. The Task Generators page reuses the same profile dropdown by importing the profiles API and rendering its own `<select>`. This avoids coupling the new page to the platform credential form's field type system.

## Risks / Trade-offs

**[Atomic migration]** → The data migration must move settings and update the poller's config source in the same deployment. Mitigation: Single Alembic migration + code change deployed together; the poller gracefully handles missing task generator records by sleeping.

**[Poll interval change latency]** → Changes to poll interval take effect after the current sleep/IDLE cycle completes, not immediately. Mitigation: Acceptable UX — the maximum delay is one poll interval (typically 60-300 seconds). Document this in the UI.

**[Single generator per type constraint]** → The `type` unique constraint means only one email generator. Mitigation: This matches current behavior (one email poller) and can be relaxed later if multi-account polling is needed.

## Migration Plan

1. **Alembic migration**: Creates `task_generator` table and migrates email credential fields
2. **Backend deploy**: Updated email poller reads from new table; new API endpoints available
3. **Frontend deploy**: New Task Generators page; simplified email credential form
4. **Rollback**: Reverse migration restores fields to email credentials; revert poller code to read from credentials
