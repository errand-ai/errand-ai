## ADDED Requirements

### Requirement: LLM model selector on settings page
The Settings page SHALL display a "LLM Model" section with a dropdown to select the active LLM model. The dropdown SHALL be populated by calling `GET /api/llm/models`. The current selection SHALL be loaded from `GET /api/settings` (key `llm_model`). If no `llm_model` setting exists, the dropdown SHALL default to `claude-haiku-4-5-20251001`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"llm_model": "<selected>"}`.

#### Scenario: Model dropdown loads with current selection
- **WHEN** the Settings page loads and the `llm_model` setting is "gpt-4o-mini"
- **THEN** the dropdown shows available models with "gpt-4o-mini" selected

#### Scenario: Model dropdown with default
- **WHEN** the Settings page loads and no `llm_model` setting exists
- **THEN** the dropdown shows available models with "claude-haiku-4-5-20251001" selected

#### Scenario: Change model selection
- **WHEN** the admin selects a different model from the dropdown
- **THEN** the frontend sends `PUT /api/settings` with the new `llm_model` value and shows a success indication

#### Scenario: Models endpoint unavailable
- **WHEN** the Settings page loads and `GET /api/llm/models` fails
- **THEN** the dropdown is disabled and an error message is displayed indicating the model list could not be loaded
