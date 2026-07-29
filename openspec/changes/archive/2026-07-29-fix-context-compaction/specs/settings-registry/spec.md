## ADDED Requirements

### Requirement: Compaction settings

The settings registry SHALL define three keys controlling context compaction in the task runner:

| Key | Type | Purpose |
|---|---|---|
| `compaction_model` | model setting | Model used for summarization calls |
| `compaction_timeout` | integer (seconds) | Timeout for the summarization call |
| `compaction_max_tokens` | integer | Maximum output tokens for the summarization call |

All three SHALL resolve through the standard env → DB → default order, with environment variables `COMPACTION_MODEL`, `COMPACTION_TIMEOUT_SECONDS` and `COMPACTION_MAX_TOKENS` respectively, so existing deployments that set them keep working.

`compaction_model` SHALL be a member of `MODEL_SETTING_KEYS`, so `normalize_model_setting_value` mirrors `model` and `model_id` on both write and read. The shared settings card writes `model_id` while the backend resolves `model`; without membership the two never meet and the resolved model is an empty string.

None of the three SHALL be marked sensitive. `compaction_model` SHALL default to empty, meaning "use the task's model".

#### Scenario: Compaction model mirrors model_id

- **WHEN** an admin sends `PUT /api/settings` with `{"compaction_model": {"provider_id": "p1", "model_id": "claude-haiku-4-5-20251001"}}`
- **THEN** the stored value carries `model` equal to `claude-haiku-4-5-20251001` alongside `model_id`

#### Scenario: Environment overrides the stored setting

- **WHEN** `COMPACTION_TIMEOUT_SECONDS` is set in the environment and `compaction_timeout` is also stored
- **THEN** resolution returns the environment value with source reported as the environment

#### Scenario: Unset keys resolve to defaults

- **WHEN** none of the three keys is stored and no matching environment variable is set
- **THEN** each resolves to its registered default, and `compaction_model` resolves to empty

#### Scenario: Timeout accepts only positive integers

- **WHEN** an admin sends `PUT /api/settings` with `{"compaction_timeout": 0}`
- **THEN** the request is rejected as invalid
