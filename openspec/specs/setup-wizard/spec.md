## Purpose

First-run setup wizard for creating an admin account and configuring initial application settings.

## Requirements

### Requirement: Setup wizard route
The frontend SHALL define a `/setup` route that renders the setup wizard. The route SHALL NOT require authentication. The wizard SHALL only be accessible when `/api/auth/status` returns `mode: "setup"`. If the mode is not `"setup"`, navigating to `/setup` SHALL redirect to `/`.

#### Scenario: Wizard accessible in setup mode
- **WHEN** the auth status is `"setup"` and a user navigates to `/setup`
- **THEN** the setup wizard is rendered

#### Scenario: Wizard blocked when not in setup mode
- **WHEN** the auth status is `"local"` and a user navigates to `/setup`
- **THEN** the user is redirected to `/`

### Requirement: Step 1 — Create admin account
The first wizard step SHALL display a form with `username` and `password` fields (with password confirmation). Submitting the form SHALL call `POST /api/setup/create-user`. On success, the returned JWT SHALL be stored in the auth store and the wizard SHALL advance to step 2.

#### Scenario: Account created successfully
- **WHEN** the user submits valid username and password
- **THEN** the backend creates the admin user, returns a JWT, and the wizard advances to step 2

#### Scenario: Passwords don't match
- **WHEN** the user submits mismatched password and confirmation
- **THEN** a client-side validation error is shown and no API call is made

### Requirement: Create first user endpoint
The backend SHALL expose `POST /api/setup/create-user` with NO authentication required. The endpoint SHALL accept `{"username": "...", "password": "..."}`, create a local admin user, and return a JWT. The endpoint SHALL return HTTP 403 if any local user already exists.

#### Scenario: First user created
- **WHEN** no local users exist and valid credentials are submitted
- **THEN** the backend creates the user and returns `{"access_token": "<jwt>", "token_type": "bearer"}`

#### Scenario: Setup already completed
- **WHEN** a local user already exists and the endpoint is called
- **THEN** the backend returns HTTP 403 with `{"detail": "Setup already completed"}`

### Requirement: Step 2 — LLM provider configuration
The second wizard step SHALL display fields for Provider Name, Provider URL, and API Key. On entering Step 2, the wizard SHALL fetch `GET /api/llm/providers`. If any provider already exists (env-sourced or database-sourced), all three fields SHALL be pre-filled from the first provider's `name`, `base_url`, and masked `api_key`, and marked as read-only. If no providers exist, all three fields SHALL be editable with Provider Name defaulting to `"default"`.

A "Test Connection" button SHALL:
1. If no env-sourced provider exists, create a provider via `POST /api/llm/providers` with the entered `name`, `base_url`, and `api_key`.
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

The third wizard step SHALL present a single model choice, populated from `GET /api/llm/providers/{id}/models` using the provider ID from Step 2. No model SHALL be selected on the user's behalf except where the provider lists exactly one, in which case that one SHALL be selected. Leaving the choice unmade SHALL be permitted and SHALL write nothing.

The step previously offered a dropdown per role, each defaulting to a named Anthropic model. A user setting up against a local runtime and touching neither dropdown had a model written against a provider that has never served it: every task then failed while the settings reported a model was configured. A default is not a neutral starting point when it names a specific vendor's model on an installation configured for a different provider.

A "Complete Setup" button SHALL apply the choice through the single model-selection operation, naming the provider and the model, and SHALL NOT write the individual settings keys. The wizard therefore does not name the roles a choice governs; which settings implement it, and how many there are, is the server's business. Writing the keys directly also bypasses validating the model against the provider's listing, which is what separates a choice from a typo.

Where the operation is refused, the step SHALL show the reason the server gave and SHALL keep the choice available to try again. A refusal here is specific — the provider is gone, or does not serve that model, or its listing could not be read — and a generic failure message would withhold the one sentence that says what to do about it.

One answer governs both the running of tasks and the classification of new ones, so the step SHALL say so. A question that decides more than it appears to is the same fault as choosing a model on the user's behalf, arrived at from the other side; stating it is also what tells the user the two roles can later be set separately, which this step deliberately does not offer.

#### Scenario: Models populated from provider

- **WHEN** the user reaches Step 3 after a successful connection test
- **THEN** the model choice shows the models available from `GET /api/llm/providers/{id}/models`
- **AND** no model is selected unless the provider listed exactly one

#### Scenario: Setup completed with provider-aware model settings

- **WHEN** the user selects a model and clicks "Complete Setup"
- **THEN** the choice is applied through the model-selection operation, naming the provider and the model
- **AND** no individual model settings keys are written by the wizard
- **AND** the user is redirected to `/settings`

#### Scenario: No model chosen writes nothing

- **WHEN** the user completes setup without choosing a model
- **THEN** no model selection is applied and no model setting is written
- **AND** setup completes

#### Scenario: A refused choice states why and stays open

- **WHEN** applying the chosen model is refused
- **THEN** the reason given by the server is shown
- **AND** the choice remains available to try again

#### Scenario: What the choice governs is disclosed

- **WHEN** the model choice is presented
- **THEN** the step states that the answer governs both the running of tasks and the classification of new ones
