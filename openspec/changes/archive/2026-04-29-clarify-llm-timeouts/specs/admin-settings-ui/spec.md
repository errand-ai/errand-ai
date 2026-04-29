## ADDED Requirements

### Requirement: Per-role timeout inputs adjacent to model selectors
The Task Management page's "LLM Models" section SHALL render three model groups — "Title generation", "Default task processing", and "Transcription" — and each group SHALL include both its model selector and a timeout input rendered immediately below the selector. Each timeout input SHALL be a number input with `min=1`, integer step, and a "seconds" suffix label. Each input SHALL bind to its respective settings key:

| Group | Settings key |
|---|---|
| Title generation | `title_generation_timeout` |
| Default task processing | `task_processing_timeout` |
| Transcription | `transcription_timeout` |

When the page is saved, the frontend SHALL include all three timeout values in the `PUT /api/settings` payload alongside the model selections. The previous standalone generic "LLM Timeout" input SHALL be removed from the page.

#### Scenario: Three timeout inputs render adjacent to model selectors
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the "LLM Models" section displays three groups, each with a model selector and a timeout input directly below it

#### Scenario: Saving sends all three timeout values
- **WHEN** an admin sets the title timeout to 20, the task processing timeout to 180, and the transcription timeout to 45 and clicks Save
- **THEN** the frontend sends `PUT /api/settings` with `title_generation_timeout: 20`, `task_processing_timeout: 180`, and `transcription_timeout: 45`

#### Scenario: Defaults shown when no settings exist
- **WHEN** an admin loads the page and none of the three timeout settings exist in the database
- **THEN** all three timeout inputs display `30`

#### Scenario: Legacy generic input removed
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** no standalone "LLM Timeout" input exists outside the per-model groups
