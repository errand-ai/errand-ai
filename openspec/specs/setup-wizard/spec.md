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
The second wizard step SHALL display fields for LLM Provider URL and API Key. If `OPENAI_BASE_URL` or `OPENAI_API_KEY` are set via environment variables, the corresponding fields SHALL be pre-filled and marked as read-only. A "Test Connection" button SHALL call `GET /api/llm/models` to verify the configuration works. On success, the wizard SHALL advance to step 3.

#### Scenario: Env var pre-fills provider URL
- **WHEN** `OPENAI_BASE_URL` is set as an env var
- **THEN** the Provider URL field is pre-filled with the value and marked read-only

#### Scenario: User enters LLM config manually
- **WHEN** no LLM env vars are set
- **THEN** both fields are editable and the user enters the values

#### Scenario: Test connection succeeds
- **WHEN** the user clicks "Test Connection" and the LLM provider responds with a model list
- **THEN** a success message is shown and the user can proceed to step 3

#### Scenario: Test connection fails
- **WHEN** the user clicks "Test Connection" and the LLM provider is unreachable
- **THEN** an error message is shown and the user cannot proceed until the config is corrected

### Requirement: Step 2 saves LLM config to database
When the user proceeds from step 2, the wizard SHALL save the LLM provider URL and API key to the database via `PUT /api/settings` with keys `openai_base_url` and `openai_api_key` (unless they are already set via env vars, in which case no save is needed).

#### Scenario: LLM config saved to DB
- **WHEN** the user enters LLM provider details and proceeds
- **THEN** the values are saved to the settings table

#### Scenario: Env-sourced LLM config not saved
- **WHEN** both LLM values come from env vars
- **THEN** no settings write occurs (env is the source of truth)

### Requirement: Step 3 — Model selection
The third wizard step SHALL display two dropdowns populated from `GET /api/llm/models`: "Title Generation Model" (admin tasks) and "Default Task Model" (task processing). The dropdowns SHALL default to `claude-haiku-4-5-20251001` and `claude-sonnet-4-5-20250929` respectively. A "Complete Setup" button SHALL save the selections via `PUT /api/settings` and redirect to the Settings page.

#### Scenario: Models populated from LLM provider
- **WHEN** step 3 loads after a successful LLM connection
- **THEN** both dropdowns show the available models from the provider

#### Scenario: Setup completed
- **WHEN** the user selects models and clicks "Complete Setup"
- **THEN** the model settings are saved and the user is redirected to `/settings`
