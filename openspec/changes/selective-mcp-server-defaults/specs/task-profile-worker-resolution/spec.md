## ADDED Requirements

### Requirement: Resolved model name accepts either `model` or `model_id`

When the resolved model setting is an object, the task manager SHALL take the model name from `model` when present and non-empty, and otherwise from `model_id`. `OPENAI_MODEL` SHALL be set to that name.

Profiles saved before the write-side mirror hold only `model_id`. Reading `model` alone yields an empty string there, and the task runner treats an empty `OPENAI_MODEL` as missing and exits with `Missing required environment variables: OPENAI_MODEL`. Accepting either key repairs those stored rows without a data migration.

#### Scenario: Object carrying only model_id

- **WHEN** the resolved model setting is `{"provider_id": null, "model_id": "claude-haiku-4-5-20251001"}`
- **THEN** `OPENAI_MODEL` is `claude-haiku-4-5-20251001`

#### Scenario: Canonical key wins when both are present and differ

- **WHEN** the resolved model setting is `{"model": "canonical", "model_id": "mirror"}`
- **THEN** `OPENAI_MODEL` is `canonical`

#### Scenario: Plain string is unaffected

- **WHEN** the resolved model setting is the string `gpt-4o`
- **THEN** `OPENAI_MODEL` is `gpt-4o`

#### Scenario: Neither key present is still an error

- **WHEN** the resolved model setting is an object carrying neither `model` nor `model_id`, and no provider is configured
- **THEN** the task fails with `LLM provider not configured` rather than launching a runner with an empty model
