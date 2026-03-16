## MODIFIED Requirements

### Requirement: Step 2 — LLM provider configuration
The second wizard step SHALL display fields for Provider Name, Provider URL, and API Key. On entering Step 2, the wizard SHALL fetch `GET /api/llm/providers`. If any provider already exists (env-sourced or database-sourced), all three fields SHALL be pre-filled from the first provider's `name`, `base_url`, and masked `api_key`, and marked as read-only. If no providers exist, all three fields SHALL be editable with Provider Name defaulting to `"default"`.

A "Test Connection" button SHALL:
1. If no env-sourced provider exists, create a provider via `POST /api/llm/providers` with `name: "default"`, the entered `base_url`, and `api_key`.
2. Fetch models from `GET /api/llm/providers/{id}/models` using the provider's ID.
3. If the model fetch succeeds, store the provider ID for use in Step 3 and show a success message.
4. If the model fetch fails and the provider was just created (not env-sourced), delete it via `DELETE /api/llm/providers/{id}` and show an error.

If an env-sourced provider already exists, "Test Connection" SHALL skip provider creation and fetch models directly from the env-sourced provider.

#### Scenario: Env-sourced provider pre-fills fields
- **WHEN** `LLM_PROVIDER_0_*` env vars are set and the wizard enters Step 2
- **THEN** the Provider URL field is pre-filled with the env-sourced provider's `base_url`, the API Key field shows the masked key, and both fields are read-only

#### Scenario: No providers exist — user enters config manually
- **WHEN** no LLM providers exist and the wizard enters Step 2
- **THEN** both fields are editable and empty

#### Scenario: Test connection succeeds with new provider
- **WHEN** the user enters a valid URL and API key and clicks "Test Connection"
- **THEN** a provider is created via `POST /api/llm/providers`, models are fetched from `GET /api/llm/providers/{id}/models`, a success message is shown, and the provider ID is retained for Step 3

#### Scenario: Test connection fails — provider cleaned up
- **WHEN** the user enters an invalid URL or API key, clicks "Test Connection", and the model fetch fails
- **THEN** the newly created provider is deleted via `DELETE /api/llm/providers/{id}` and an error message is shown

#### Scenario: Test connection with env-sourced provider
- **WHEN** an env-sourced provider exists and the user clicks "Test Connection"
- **THEN** models are fetched from `GET /api/llm/providers/{id}/models` without creating a new provider

### Requirement: Step 2 saves LLM config to database
When the user proceeds from Step 2, the LLM provider SHALL already exist in the `llm_providers` table — either created via `POST /api/llm/providers` during "Test Connection" or pre-existing from env var scanning. The wizard SHALL NOT write `openai_base_url` or `openai_api_key` to the settings table.

#### Scenario: Provider created during test connection
- **WHEN** the user tested the connection successfully and proceeds to Step 3
- **THEN** the provider already exists in `llm_providers` with `source: "database"`

#### Scenario: Env-sourced provider — no write needed
- **WHEN** the provider came from env vars and the user proceeds to Step 3
- **THEN** no new provider is created (the env-sourced provider is used)

### Requirement: Step 3 — Model selection
The third wizard step SHALL display two dropdowns for "Title Generation Model" and "Default Task Model". The dropdowns SHALL be populated from `GET /api/llm/providers/{id}/models` using the provider ID from Step 2. The dropdowns SHALL default to `claude-haiku-4-5-20251001` and `claude-sonnet-4-5-20250929` respectively. A "Complete Setup" button SHALL save the selections via `PUT /api/settings` as `{provider_id: "<uuid>", model: "<model-id>"}` objects for keys `llm_model` and `task_processing_model`, then redirect to the Settings page.

#### Scenario: Models populated from provider
- **WHEN** Step 3 loads after a successful LLM connection in Step 2
- **THEN** both dropdowns show the available models from `GET /api/llm/providers/{id}/models`

#### Scenario: Setup completed with provider-aware model settings
- **WHEN** the user selects models and clicks "Complete Setup"
- **THEN** `llm_model` is saved as `{"provider_id": "<uuid>", "model": "<selected-title-model>"}` and `task_processing_model` is saved as `{"provider_id": "<uuid>", "model": "<selected-task-model>"}` via `PUT /api/settings`, and the user is redirected to `/settings`
