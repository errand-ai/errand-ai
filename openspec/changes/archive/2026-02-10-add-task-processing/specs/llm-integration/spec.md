## ADDED Requirements

### Requirement: OpenAI SDK client configuration
The backend SHALL create an async OpenAI client using the `openai` Python SDK with `base_url` set to the `LITELLM_BASE_URL` environment variable and `api_key` set to the `LITELLM_API_KEY` environment variable. The client SHALL be initialized during application startup. If either environment variable is missing, the client SHALL not be created and LLM features SHALL degrade gracefully.

#### Scenario: Client initialized with env vars
- **WHEN** the backend starts with `LITELLM_BASE_URL=http://litellm:4000` and `LITELLM_API_KEY=sk-xxx`
- **THEN** an async OpenAI client is created with those values

#### Scenario: Missing env vars
- **WHEN** the backend starts without `LITELLM_BASE_URL`
- **THEN** no OpenAI client is created and LLM features use fallback behavior

### Requirement: LLM title generation from task description
When a new task is created with an input longer than 5 words, the backend SHALL call the LLM to generate a short title (2-5 words) summarizing the description. The LLM call SHALL use the `chat.completions.create` method with the model from the `llm_model` setting (default: `claude-haiku-4-5-20251001`). The system prompt SHALL instruct the model to summarize the task into a short title. The call SHALL have a 5-second timeout.

#### Scenario: Successful title generation
- **WHEN** a task is created with input "The login page throws a 500 error when users with special characters try to reset their password"
- **THEN** the backend calls the LLM and stores the response as the task title and the input as the task description

#### Scenario: LLM call fails
- **WHEN** a task is created with a long input and the LLM call fails or times out
- **THEN** the task is created with the first 5 words of the input plus "..." as the title, the full input as the description, and a "Needs Info" tag is applied

#### Scenario: LLM client not available
- **WHEN** a task is created with a long input but the OpenAI client was not initialized (missing env vars)
- **THEN** the task uses the fallback title (first 5 words + "...") and gets a "Needs Info" tag

### Requirement: Short input treated as title
When a new task is created with an input of 5 words or fewer, the backend SHALL use the input as the task title directly (no LLM call). A "Needs Info" tag SHALL be automatically applied to the task.

#### Scenario: Short input becomes title
- **WHEN** a task is created with input "Fix login bug"
- **THEN** the task title is "Fix login bug", the description is null, and the tag "Needs Info" is applied

### Requirement: Default LLM model
The backend SHALL use the `llm_model` setting value as the model for LLM calls. If no `llm_model` setting exists in the database, the backend SHALL default to `claude-haiku-4-5-20251001`.

#### Scenario: Custom model configured
- **WHEN** the `llm_model` setting is "gpt-4o-mini"
- **THEN** LLM calls use model "gpt-4o-mini"

#### Scenario: No model configured
- **WHEN** no `llm_model` setting exists
- **THEN** LLM calls use model "claude-haiku-4-5-20251001"

### Requirement: Model list proxy endpoint
The backend SHALL expose `GET /api/llm/models` requiring the `admin` role. The endpoint SHALL call `LITELLM_BASE_URL/v1/models` using the OpenAI client and return the list of available model IDs as a JSON array of strings.

#### Scenario: Models retrieved successfully
- **WHEN** an admin requests `GET /api/llm/models` and LiteLLM returns a list of models
- **THEN** the backend returns HTTP 200 with a JSON array of model ID strings

#### Scenario: LiteLLM unavailable
- **WHEN** an admin requests `GET /api/llm/models` and the LiteLLM call fails
- **THEN** the backend returns HTTP 502 with an error message

#### Scenario: Non-admin user
- **WHEN** a non-admin user requests `GET /api/llm/models`
- **THEN** the backend returns HTTP 403

#### Scenario: LLM client not configured
- **WHEN** an admin requests `GET /api/llm/models` but the OpenAI client is not initialized
- **THEN** the backend returns HTTP 503 with a message indicating LLM is not configured
