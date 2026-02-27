## Purpose

Optional LiteLLM container as a managed service for the macOS app, with toggle and model provider configuration.

## Requirements

### Requirement: LiteLLM as an optional managed service
The app SHALL support running a LiteLLM container as an optional service, toggled on/off in settings. When enabled, LiteLLM SHALL be started before the backend and worker, and the backend and worker SHALL use LiteLLM's URL as their `OPENAI_BASE_URL`. When disabled, the backend and worker SHALL use the user's direct `OPENAI_BASE_URL` from settings.

#### Scenario: LiteLLM enabled
- **WHEN** LiteLLM is enabled in settings and "Start All" is triggered
- **THEN** the LiteLLM container starts, and the backend and worker receive `OPENAI_BASE_URL=http://<litellm-ip>:4000`

#### Scenario: LiteLLM disabled
- **WHEN** LiteLLM is disabled in settings and "Start All" is triggered
- **THEN** no LiteLLM container is started, and the backend and worker use the direct `OPENAI_BASE_URL` from settings

### Requirement: LiteLLM configuration
The app SHALL provide a configuration interface for LiteLLM model mappings. The LiteLLM config file SHALL be stored at `~/Library/Application Support/ContentManager/data/litellm/config.yaml` and mounted into the LiteLLM container. The settings UI SHALL allow adding/removing model providers (OpenAI, Anthropic, Ollama, etc.) with their API keys and base URLs.

#### Scenario: Add Ollama provider
- **WHEN** the user adds an Ollama provider in the LiteLLM settings with base URL `http://localhost:11434`
- **THEN** the LiteLLM config is updated and the LiteLLM service can proxy requests to the local Ollama instance

#### Scenario: Config persists across restarts
- **WHEN** the user configures LiteLLM and restarts the app
- **THEN** the LiteLLM config is loaded from the persisted `config.yaml`
