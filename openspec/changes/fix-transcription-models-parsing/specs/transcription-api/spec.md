## MODIFIED Requirements

### Requirement: Transcription models endpoint

The backend SHALL expose `GET /api/llm/transcription-models` requiring the `admin` role. The endpoint SHALL query the LiteLLM proxy's `/model/info` endpoint (derived from `OPENAI_BASE_URL` by replacing the `/v1` suffix). The LiteLLM response contains a `data` field that is a JSON array of model objects, where each object has a `model_name` string and a `model_info` object. The endpoint SHALL iterate over this array and collect the `model_name` from each entry where `model_info.mode` equals `"audio_transcription"`. The endpoint SHALL return a JSON array of model name strings, sorted alphabetically. If the LiteLLM proxy is unreachable or returns an unparseable response, the endpoint SHALL return HTTP 502.

#### Scenario: Transcription models available
- **WHEN** an admin sends `GET /api/llm/transcription-models` and the LiteLLM proxy has models with `mode: audio_transcription`
- **THEN** the endpoint returns HTTP 200 with a JSON array of transcription model IDs (e.g. `["groq/whisper-large-v3", "whisper-1"]`)

#### Scenario: No transcription models configured
- **WHEN** an admin sends `GET /api/llm/transcription-models` and no models have `mode: audio_transcription`
- **THEN** the endpoint returns HTTP 200 with an empty array `[]`

#### Scenario: LiteLLM proxy unreachable
- **WHEN** the `/model/info` request to the LiteLLM proxy fails
- **THEN** the endpoint returns HTTP 502 with `{"detail": "Failed to fetch model info from LLM provider"}`

#### Scenario: LiteLLM returns unparseable response
- **WHEN** the `/model/info` response has an unexpected format
- **THEN** the endpoint returns HTTP 502 with `{"detail": "Failed to fetch model info from LLM provider"}`

#### Scenario: Non-admin user
- **WHEN** a non-admin user sends `GET /api/llm/transcription-models`
- **THEN** the backend returns HTTP 403
