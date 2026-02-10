## ADDED Requirements

### Requirement: LLM model list proxy endpoint
The backend SHALL expose `GET /api/llm/models` requiring the `admin` role. The endpoint SHALL use the OpenAI client to list available models and return their IDs as a JSON array of strings, sorted alphabetically.

#### Scenario: Models retrieved successfully
- **WHEN** an admin requests `GET /api/llm/models`
- **THEN** the backend returns HTTP 200 with a JSON array of model ID strings (e.g., `["claude-haiku-4-5-20251001", "gpt-4o-mini"]`)

#### Scenario: LiteLLM unavailable
- **WHEN** an admin requests `GET /api/llm/models` and the LiteLLM API call fails
- **THEN** the backend returns HTTP 502 with `{"detail": "Failed to fetch models from LLM provider"}`

#### Scenario: Non-admin user
- **WHEN** a non-admin user requests `GET /api/llm/models`
- **THEN** the backend returns HTTP 403 with `{"detail": "Admin role required"}`

#### Scenario: LLM client not configured
- **WHEN** an admin requests `GET /api/llm/models` but `LITELLM_BASE_URL` is not configured
- **THEN** the backend returns HTTP 503 with `{"detail": "LLM provider not configured"}`
