## ADDED Requirements

### Requirement: LLM Providers section in Task Management settings
The Task Management settings page SHALL display an "LLM Providers" section above the existing "LLM Models" section. The section SHALL show a table of configured providers with columns: Name, Base URL, Type, Source, and Actions. API keys SHALL NOT be displayed in the table. Providers with `source: "env"` SHALL display an "ENV" badge and SHALL NOT have Edit or Delete action buttons. The default provider SHALL display a star icon or "Default" badge.

#### Scenario: Providers table displayed
- **WHEN** an admin navigates to Task Management settings and providers exist
- **THEN** the LLM Providers section shows a table with all providers, default provider first

#### Scenario: Env-sourced provider is readonly
- **WHEN** a provider has `source: "env"`
- **THEN** it displays an "ENV" badge and has no Edit or Delete buttons

#### Scenario: Default provider badge shown
- **WHEN** a provider has `is_default: true`
- **THEN** it displays a "Default" badge or star icon

### Requirement: Add provider dialog
The "LLM Providers" section SHALL include an "Add Provider" button that opens a modal dialog. The dialog SHALL contain fields: Name (text input, required), Base URL (text input, required), API Key (password input, required). On submit, the dialog SHALL call `POST /api/llm/providers` and display a toast notification on success or error. The dialog SHALL show the detected provider type after creation.

#### Scenario: Add provider successfully
- **WHEN** an admin fills in name, base URL, and API key and submits
- **THEN** the provider is created, the table refreshes, and a success toast appears

#### Scenario: Duplicate name error
- **WHEN** an admin submits a provider with a name that already exists
- **THEN** an error toast shows "Provider name already exists"

### Requirement: Edit provider dialog
Each database-sourced provider row SHALL have an "Edit" button that opens a modal dialog pre-filled with the provider's current name and base URL. The API key field SHALL be empty with placeholder text "Leave blank to keep current key". On submit, the dialog SHALL call `PUT /api/llm/providers/{id}`. If the base URL changed, the provider type SHALL be re-probed (reflected in the updated response).

#### Scenario: Edit provider name
- **WHEN** an admin edits a provider's name and submits
- **THEN** the provider is updated and the table refreshes

#### Scenario: Edit provider without changing API key
- **WHEN** an admin edits a provider leaving the API key field blank
- **THEN** the existing API key is preserved

### Requirement: Delete provider with confirmation
Each non-default database-sourced provider row SHALL have a "Delete" button. Clicking it SHALL show a confirmation dialog. If the provider is referenced by any model settings, the confirmation SHALL warn: "Deleting this provider will clear the following model configurations: [list of affected settings]. You will need to reconfigure them." On confirmation, the dialog SHALL call `DELETE /api/llm/providers/{id}` and refresh both the providers table and model settings.

#### Scenario: Delete unreferenced provider
- **WHEN** an admin deletes a provider not referenced by any model setting
- **THEN** the provider is removed without warnings about model settings

#### Scenario: Delete provider referenced by models
- **WHEN** an admin deletes a provider referenced by `llm_model`
- **THEN** the confirmation warns about affected model settings
- **THEN** after confirmation, the provider is deleted and `llm_model` is cleared

#### Scenario: Cannot delete default provider
- **WHEN** a provider is the default
- **THEN** the Delete button is not shown

### Requirement: Default provider selector
The "LLM Providers" section SHALL include a "Set as Default" action button on non-default provider rows. Clicking it SHALL call `PUT /api/llm/providers/{id}/default` and refresh the table.

#### Scenario: Set new default provider
- **WHEN** an admin clicks "Set as Default" on a non-default provider
- **THEN** that provider becomes the default, the previous default loses its badge, and the table re-sorts

### Requirement: Provider dropdown on model selectors
Each model selector (Title Generation, Task Processing, Transcription) in the "LLM Models" section SHALL display a provider dropdown to the left of the model selector. The provider dropdown SHALL list all configured providers by name. When a provider is selected, the model dropdown SHALL fetch models from `GET /api/llm/providers/{id}/models` (with `?mode=audio_transcription` for the transcription selector on LiteLLM providers). For `unknown` providers, the model selector SHALL render as a free-text input instead of a dropdown. Saving a model setting SHALL persist `{provider_id, model}`.

#### Scenario: Select provider then model
- **WHEN** an admin selects "OpenAI" from the provider dropdown for Title Generation
- **THEN** the model dropdown fetches and displays models from the OpenAI provider

#### Scenario: Unknown provider shows free-text input
- **WHEN** an admin selects a provider with type `unknown` for any model role
- **THEN** the model selector renders as a text input instead of a dropdown

#### Scenario: Cleared model setting shows empty state
- **WHEN** a model setting has been cleared (provider was deleted)
- **THEN** both provider and model selectors show placeholder text prompting the user to select

#### Scenario: Transcription model dropdown for LiteLLM
- **WHEN** an admin selects a LiteLLM provider for the transcription model
- **THEN** the model dropdown fetches models with `?mode=audio_transcription`

#### Scenario: Transcription model dropdown for non-LiteLLM
- **WHEN** an admin selects an OpenAI-compatible provider for the transcription model
- **THEN** the model dropdown shows all models (unfiltered)
