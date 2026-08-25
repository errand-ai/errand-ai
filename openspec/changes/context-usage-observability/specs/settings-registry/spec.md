## MODIFIED Requirements

### Requirement: Compaction settings

The settings registry SHALL define four keys controlling context compaction in the task runner:

| Key | Type | Purpose |
|---|---|---|
| `max_context_tokens` | integer | Context ceiling: the compaction trigger, and the denominator for pressure thresholds |
| `compaction_model` | model setting | Model used for summarization calls |
| `compaction_timeout` | integer (seconds) | Timeout for the summarization call |
| `compaction_max_tokens` | integer | Maximum output tokens for the summarization call |

All four SHALL resolve through the standard env → DB → default order, with environment variables `MAX_CONTEXT_TOKENS`, `COMPACTION_MODEL`, `COMPACTION_TIMEOUT_SECONDS` and `COMPACTION_MAX_TOKENS` respectively, so existing deployments that set them keep working.

All four SHALL be presented together in the settings UI. `max_context_tokens` is the threshold the other three respond to; separating them would put the trigger and its handling on different screens.

`compaction_model` SHALL be a member of `MODEL_SETTING_KEYS`, so `normalize_model_setting_value` mirrors `model` and `model_id` on both write and read. The shared settings card writes `model_id` while the backend resolves `model`; without membership the two never meet and the resolved model is an empty string.

None of the four SHALL be marked sensitive. `compaction_model` SHALL default to empty, meaning "use the task's model". `max_context_tokens` SHALL default to 150000.

#### Scenario: Context ceiling is editable from the settings UI

- **WHEN** an admin opens the compaction settings card
- **THEN** `max_context_tokens` is presented alongside the three compaction settings
- **THEN** changing it updates the value the task runner receives as `MAX_CONTEXT_TOKENS`

#### Scenario: Compaction model mirrors model_id

- **WHEN** an admin sends `PUT /api/settings` with `{"compaction_model": {"provider_id": "p1", "model_id": "claude-haiku-4-5-20251001"}}`
- **THEN** the stored value carries `model` equal to `claude-haiku-4-5-20251001` alongside `model_id`

#### Scenario: Environment overrides the stored setting

- **WHEN** `COMPACTION_TIMEOUT_SECONDS` is set in the environment and `compaction_timeout` is also stored
- **THEN** resolution returns the environment value with source reported as the environment

#### Scenario: Ceiling default applies when unset

- **WHEN** neither `MAX_CONTEXT_TOKENS` nor a stored `max_context_tokens` is present
- **THEN** resolution returns 150000
