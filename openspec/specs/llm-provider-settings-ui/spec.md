## Purpose

The admin settings UI for configuring LLM providers, including reasoning-model support and warnings when a non-reasoning model is set as the default.

## Requirements

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
Each model selector (Title Generation, Task Processing, Transcription) in the "LLM Models" section SHALL display a provider dropdown to the left of the model selector. The provider dropdown SHALL list all configured providers by name. When a provider is selected, the model dropdown SHALL fetch models from `GET /api/llm/providers/{id}/models` (with `?mode=audio_transcription` for the transcription selector on LiteLLM providers). The model list endpoint SHALL return an array of objects with fields: `id` (string, the model name), `supports_reasoning` (boolean or null), `max_output_tokens` (integer or null). For `unknown` providers, the model selector SHALL render as a free-text input instead of a dropdown. Saving a model setting SHALL persist `{provider_id, model}`.

When a model with `supports_reasoning: true` is selected for the Title Generation model role, the UI SHALL display an inline warning below the model selector: "This is a reasoning model. It may be slower and less reliable for structured output tasks like title generation. Consider using a non-reasoning model." The warning SHALL be styled as a cautionary notice (amber/yellow). No warning SHALL be shown for models with `supports_reasoning: false` or `supports_reasoning: null`.

When a model with `supports_reasoning: false` is selected for the Task Processing (Default Model) role, the UI SHALL display an inline warning below the model selector: "This is not a reasoning model. Reasoning models are recommended for task processing to support complex workflows and tool calling. Consider using a reasoning model." The warning SHALL be styled as a cautionary notice (amber/yellow). No warning SHALL be shown for models with `supports_reasoning: true` or `supports_reasoning: null`.

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

#### Scenario: Reasoning model warning shown for title generation
- **WHEN** an admin selects a model with `supports_reasoning: true` for the Title Generation role
- **THEN** an amber inline warning is displayed below the model selector advising that reasoning models may be slower and less reliable for structured output

#### Scenario: No warning for non-reasoning title generation model
- **WHEN** an admin selects a model with `supports_reasoning: false` for Title Generation
- **THEN** no warning is displayed

#### Scenario: No warning for unknown title generation model
- **WHEN** an admin selects a model with `supports_reasoning: null` (not in metadata cache) for Title Generation
- **THEN** no warning is displayed

#### Scenario: Non-reasoning warning shown for default model
- **WHEN** an admin selects a model with `supports_reasoning: false` for the Default Model (Task Processing) role
- **THEN** an amber inline warning is displayed below the model selector advising that reasoning models are recommended for task processing

#### Scenario: No warning for reasoning default model
- **WHEN** an admin selects a model with `supports_reasoning: true` for the Default Model
- **THEN** no warning is displayed

#### Scenario: No warning for unknown default model
- **WHEN** an admin selects a model with `supports_reasoning: null` for the Default Model
- **THEN** no warning is displayed

#### Scenario: Model list returns enriched objects
- **WHEN** the model dropdown fetches models from `GET /api/llm/providers/{id}/models`
- **THEN** each item in the response is an object with `id`, `supports_reasoning`, and `max_output_tokens` fields

### Requirement: Providers are added by choosing from a catalog

The provider settings UI SHALL offer a list of known providers to choose from when adding a provider, rather than requiring a base URL to be typed. Choosing a listed provider SHALL require only an API key. The list SHALL include an explicit entry for an unlisted OpenAI-compatible provider.

#### Scenario: Adding a listed provider

- **WHEN** the user adds a provider and selects a listed entry
- **THEN** only an API key is requested
- **AND** the base URL is taken from the catalog entry

#### Scenario: Adding an unlisted provider

- **WHEN** the user selects the unlisted OpenAI-compatible entry
- **THEN** fields for a base URL and an API key are revealed
- **AND** both are required before the provider can be saved

#### Scenario: Key acquisition is signposted

- **WHEN** a listed provider is selected
- **THEN** the UI links to where that provider's API key is obtained

### Requirement: Model browsing adapts to model-listing support

The provider settings UI SHALL let a user find out which models a configured provider offers. Where the provider supports model listing, the retrieved models SHALL be presented. Where it declares no model-listing support, or listing fails, the UI SHALL accept a directly entered model name so that the user can still establish a usable name, rather than being left with nothing.

This control browses; it does not store a selection. `llm_providers` has no model column and nothing persists a model against a provider — per-role model choices are saved by the LLM models settings card, against the `llm_model`, `task_processing_model` and `transcription_model` settings. The question this control answers is "what may I name for this provider?", and no more.

#### Scenario: Provider supports listing

- **WHEN** a provider that supports model listing is configured
- **THEN** its models are presented

#### Scenario: Provider does not support listing

- **WHEN** the selected provider declares no model-listing support
- **THEN** a model name can be entered directly

#### Scenario: Listing fails at runtime

- **WHEN** model listing is attempted and fails
- **THEN** the UI offers direct entry and explains why the list is unavailable
- **AND** does not leave the control looking as though it is still loading

#### Scenario: Long model lists remain usable

- **WHEN** a provider returns a large number of models
- **THEN** the selection control supports filtering by typing rather than requiring scrolling through the whole list

### Requirement: Local AI runtimes can be discovered from the UI

The provider settings UI SHALL offer a control that scans for local AI runtimes and presents what was found for the user to adopt. Where detection is unavailable for the deployment, the control SHALL explain that rather than appearing broken.

#### Scenario: Scan finds runtimes

- **WHEN** the user runs a scan and local runtimes are found
- **THEN** they are presented with their name and endpoint

#### Scenario: Scan finds nothing

- **WHEN** the user runs a scan and nothing responds
- **THEN** the UI reports that no local AI was found, without presenting an error

#### Scenario: Detection unavailable

- **WHEN** the deployment cannot reach a container host
- **THEN** the scan control explains that local detection is not available for this deployment

### Requirement: Provider reachability is visible

The provider settings UI SHALL show whether each configured provider is currently reachable, and SHALL offer a way to re-check. A provider whose backing service has stopped SHALL be visibly distinguishable from a working one.

#### Scenario: Unreachable provider is marked

- **WHEN** a configured provider's service is not responding
- **THEN** the UI shows it as unreachable

#### Scenario: Re-check available

- **WHEN** the user re-checks a provider
- **THEN** its reachability state is refreshed
- **AND** its stored configuration is unchanged

### Requirement: Detected providers are identified as such

Providers created by local detection SHALL be visibly distinguished from manually configured ones, and the UI SHALL indicate that they are reconciled by scanning rather than edited by hand.

#### Scenario: Detected provider labelled

- **WHEN** a detected provider is listed
- **THEN** it is shown as detected rather than as a manually configured provider
