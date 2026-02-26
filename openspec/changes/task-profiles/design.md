## Context

Tasks currently share a single agent configuration: one model (`task_processing_model`), one system prompt, one set of MCP servers, one set of skills. These are global settings managed across Agent Configuration and Task Management sub-pages. The worker reads them in `read_settings()` and passes them to every task runner container identically.

The existing `category` field (`immediate/scheduled/repeating`) controls *when* a task runs. Task profiles control *how* it runs — which model, tools, and instructions the agent gets.

## Goals / Non-Goals

**Goals:**
- Let users define named agent configuration presets (task profiles)
- Automatic LLM-based profile assignment during task creation
- Cost optimization by matching tasks to appropriate models
- Inheritance model: custom profiles override specific settings, inherit the rest from the virtual default
- Three-state list fields: `null` = inherit all, `[]` = none, `["x"]` = explicit subset
- Profile resolved at execution time (not snapshot) so repeating tasks pick up profile changes

**Non-Goals:**
- Per-task ad-hoc configuration (profiles are reusable presets, not one-off overrides)
- Nesting profiles (no profile-inherits-from-profile chains — only default → custom)
- Auto-creating profiles (users define them manually; the system only auto-assigns)
- Changing existing global settings behavior (the default profile remains virtual)

## Decisions

### 1. Virtual default profile

**Decision**: The "default" profile is not a database row. It is the current global settings composed at runtime: `task_processing_model`, `system_prompt`, `mcp_servers`, skills, etc. Custom profiles stored in the `task_profiles` table override specific fields.

**Rationale**: Global settings are already spread across multiple settings sub-pages (Agent Configuration, Task Management). Making default a DB row would require migrating settings into it or maintaining dual sources of truth. Virtual default keeps existing behavior untouched.

**Consequence**: When the worker resolves a profile, it first reads global settings (as today), then overlays profile-specific overrides. For tasks with `profile_id = null`, the result is identical to current behavior.

### 2. Three-state list field semantics

**Decision**: For list fields (`mcp_servers`, `litellm_mcp_servers`, `skills`):
- `null` (SQL NULL / JSON null) → inherit from default (all configured)
- `[]` (empty array) → explicitly none (no tools/skills)
- `["x", "y"]` → explicit subset

**Rationale**: Distinguishing "inherit" from "empty" is essential. An email-triage profile might want no MCP servers except gmail (`["gmail"]`), while a coding profile might want all default servers (`null`) plus specific overrides. Without the `null` vs `[]` distinction, you can't express "remove all" — you'd always inherit.

**Storage**: JSON columns in PostgreSQL. NULL at the SQL level means inherit. An empty JSON array means explicitly empty.

### 3. LLM classification with match rules

**Decision**: Each profile has a `match_rules` text field — free-form natural language describing when the profile should match. At task creation, the existing `generate_title` LLM call is extended to also select a profile. The profiles' names and match rules are injected into the classifier system prompt.

**Rationale**: The LLM is already classifying tasks (category + timing). Adding profile selection is a natural extension. Free-form rules are the most flexible — the user writes what they mean, the LLM interprets it.

**Fallback**: If the LLM doesn't select a profile or selects an unknown one, the task uses the default profile. If the LLM fails entirely, the task goes to Review (existing behavior) where the user can set the profile manually.

### 4. Profile resolution at execution time

**Decision**: The Task model stores only `profile_id` (FK). The worker resolves the full configuration when dequeuing the task by reading the profile row and applying inheritance.

**Rationale**: This means profile changes (e.g., upgrading the model) automatically apply to future runs of repeating tasks. No need to update every pending task when a profile changes.

**Trade-off**: If a profile is deleted while tasks reference it, the worker needs a fallback. Decision: if `profile_id` references a non-existent profile, treat as default (log a warning).

### 5. TaskProfile database model

**Decision**: New `task_profiles` table with columns:

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| name | Text | Unique, user-facing identifier |
| description | Text | For display in UI and LLM prompt |
| match_rules | Text | Free-form text for LLM classifier |
| model | Text (nullable) | Override `task_processing_model` |
| system_prompt | Text (nullable) | Override global system prompt |
| max_turns | Integer (nullable) | Override MAX_TURNS |
| reasoning_effort | Text (nullable) | Override: low/medium/high |
| mcp_servers | JSON (nullable) | Override: null=inherit, []=none, [names]=subset |
| litellm_mcp_servers | JSON (nullable) | Override: null=inherit, []=none, [aliases]=subset |
| skill_ids | JSON (nullable) | Override: null=inherit, []=none, [uuids]=subset |
| created_at | Timestamptz | Auto |
| updated_at | Timestamptz | Auto |

The `tasks` table gains a nullable `profile_id` UUID FK to `task_profiles.id` (SET NULL on delete — if profile deleted, task reverts to default).

### 6. Profile in MCP tools and future sources

**Decision**: The `schedule_task` MCP tool gains an optional `profile` parameter (string, the profile name). The `new_task` tool continues to use LLM classification for profile selection. Future task sources (webhooks, mailbox polling) will have profile configuration as part of their integration settings.

**Rationale**: `schedule_task` is for explicit, programmatic task creation — the caller knows what kind of task it is. `new_task` is for ad-hoc descriptions where the LLM should decide.

### 7. Settings navigation placement

**Decision**: "Task Profiles" becomes a new settings sub-page at `/settings/profiles`, between "Task Management" and "Security" in the sidebar.

## Risks / Trade-offs

- **[Prompt bloat]** Many profiles with long match rules could bloat the classifier prompt → Mitigation: keep match rules concise (UI guidance), truncate at reasonable limit. With 5-10 profiles the prompt stays manageable.
- **[Classification accuracy]** The LLM might misassign profiles for ambiguous tasks → Mitigation: tasks go to Review on uncertainty; users can always override. Repeating tasks are set once and reused.
- **[Profile deletion with active tasks]** Deleting a profile that tasks reference → Mitigation: `ON DELETE SET NULL` — tasks revert to default profile. UI could show a warning with task count.
- **[Stale skill_ids]** Profile references skill UUIDs that may be deleted → Mitigation: at resolution time, filter to existing skills. Missing skill IDs are silently ignored.
