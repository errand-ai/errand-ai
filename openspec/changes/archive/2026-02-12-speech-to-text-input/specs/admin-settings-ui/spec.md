## MODIFIED Requirements

### Requirement: LLM model selector on settings page

_(Append to existing requirement — transcription model selector with filtered list)_

The "LLM Models" section SHALL display a third dropdown labelled "Transcription Model" for selecting the speech-to-text model. The dropdown SHALL be populated by calling `GET /api/llm/transcription-models` (NOT the generic `/api/llm/models` endpoint) which returns only models with audio transcription capability. The current selection SHALL be loaded from `GET /api/settings` (key `transcription_model`). If no `transcription_model` setting exists, the dropdown SHALL show a placeholder "Select a model to enable voice input" with no model selected. Selecting a model SHALL immediately save the choice via `PUT /api/settings` with `{"transcription_model": "<selected>"}`.

The dropdown SHALL also include a "Disabled" option that, when selected, removes the `transcription_model` setting (sends `PUT /api/settings` with `{"transcription_model": null}`), disabling voice input for all users.

#### Scenario: No transcription model selected (default)
- **WHEN** the Settings page loads and no `transcription_model` setting exists
- **THEN** the "Transcription Model" dropdown shows placeholder "Select a model to enable voice input" with no model selected

#### Scenario: Transcription model selected
- **WHEN** the Settings page loads and the `transcription_model` setting is `groq/whisper-large-v3`
- **THEN** the "Transcription Model" dropdown shows `groq/whisper-large-v3` as selected

#### Scenario: Select transcription model
- **WHEN** the admin selects `whisper-1` from the "Transcription Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"transcription_model": "whisper-1"}` and shows a success indication

#### Scenario: Disable transcription
- **WHEN** the admin selects "Disabled" from the "Transcription Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"transcription_model": null}` to remove the setting, disabling voice input

#### Scenario: Only transcription-capable models shown
- **WHEN** the Settings page loads the transcription model dropdown
- **THEN** only models with `mode: audio_transcription` from the LiteLLM proxy are shown (not general chat or embedding models)

#### Scenario: No transcription models available
- **WHEN** `GET /api/llm/transcription-models` returns an empty array
- **THEN** the dropdown is disabled and shows "No transcription models available"

#### Scenario: Transcription models endpoint unavailable
- **WHEN** `GET /api/llm/transcription-models` fails
- **THEN** the dropdown is disabled and an error message is displayed
