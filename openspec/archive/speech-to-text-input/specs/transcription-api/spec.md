## ADDED Requirements

### Requirement: Transcription endpoint

The backend SHALL expose `POST /api/transcribe` requiring an authenticated user. The endpoint SHALL accept a multipart file upload with field name `file`. The endpoint SHALL check that a `transcription_model` setting exists in the database. If no setting exists, the endpoint SHALL return HTTP 503 with `{"detail": "Transcription not configured"}`. Otherwise, the endpoint SHALL forward the audio file to the LLM provider via the OpenAI SDK's `client.audio.transcriptions.create()` method using the configured model. The endpoint SHALL return a JSON object `{"text": "<transcript>"}` with HTTP 200.

#### Scenario: Successful transcription
- **WHEN** an authenticated user sends `POST /api/transcribe` with a valid audio file and a `transcription_model` setting exists
- **THEN** the backend returns HTTP 200 with `{"text": "Schedule a meeting with the team"}`

#### Scenario: Transcription not configured
- **WHEN** a user sends `POST /api/transcribe` and no `transcription_model` setting exists in the database
- **THEN** the backend returns HTTP 503 with `{"detail": "Transcription not configured"}`

#### Scenario: Empty transcript
- **WHEN** the audio contains only silence or unintelligible sound
- **THEN** the backend returns HTTP 200 with `{"text": ""}` (empty string from the STT model)

#### Scenario: Unauthenticated request
- **WHEN** a request is sent without a valid Bearer token
- **THEN** the backend returns HTTP 401

#### Scenario: No file uploaded
- **WHEN** a request is sent without a file field
- **THEN** the backend returns HTTP 422 (FastAPI validation error)

### Requirement: Transcription status endpoint

The backend SHALL expose `GET /api/transcribe/status` requiring any authenticated user. The endpoint SHALL check whether a `transcription_model` setting exists in the database and whether the LLM client is configured. The endpoint SHALL return `{"enabled": true}` if both conditions are met, and `{"enabled": false}` otherwise.

#### Scenario: Transcription enabled
- **WHEN** the `transcription_model` setting exists and the LLM client is configured
- **THEN** `GET /api/transcribe/status` returns `{"enabled": true}`

#### Scenario: Transcription not configured (no model selected)
- **WHEN** no `transcription_model` setting exists
- **THEN** `GET /api/transcribe/status` returns `{"enabled": false}`

#### Scenario: LLM client not configured
- **WHEN** `OPENAI_BASE_URL` is not set
- **THEN** `GET /api/transcribe/status` returns `{"enabled": false}`

### Requirement: Transcription error handling

If the LLM client is not configured (no `OPENAI_BASE_URL`), the transcribe endpoint SHALL return HTTP 503 with `{"detail": "LLM provider not configured"}`. If the transcription API call fails, the endpoint SHALL return HTTP 502 with `{"detail": "Transcription failed"}`.

#### Scenario: LLM client not configured
- **WHEN** `OPENAI_BASE_URL` is not set and a user sends `POST /api/transcribe`
- **THEN** the backend returns HTTP 503 with `{"detail": "LLM provider not configured"}`

#### Scenario: Transcription API failure
- **WHEN** the LLM provider returns an error during transcription
- **THEN** the backend returns HTTP 502 with `{"detail": "Transcription failed"}`

### Requirement: Transcription models endpoint

The backend SHALL expose `GET /api/llm/transcription-models` requiring the `admin` role. The endpoint SHALL query the LiteLLM proxy's `/model/info` endpoint (derived from `OPENAI_BASE_URL` by replacing the `/v1` suffix) and return only models where the `mode` field equals `"audio_transcription"`. The endpoint SHALL return a JSON array of model ID strings, sorted alphabetically.

#### Scenario: Transcription models available
- **WHEN** an admin sends `GET /api/llm/transcription-models` and the LiteLLM proxy has models with `mode: audio_transcription`
- **THEN** the endpoint returns HTTP 200 with a JSON array of transcription model IDs (e.g. `["groq/whisper-large-v3", "whisper-1"]`)

#### Scenario: No transcription models configured
- **WHEN** an admin sends `GET /api/llm/transcription-models` and no models have `mode: audio_transcription`
- **THEN** the endpoint returns HTTP 200 with an empty array `[]`

#### Scenario: LiteLLM proxy unreachable
- **WHEN** the `/model/info` request to the LiteLLM proxy fails
- **THEN** the endpoint returns HTTP 502 with `{"detail": "Failed to fetch models from LLM provider"}`

#### Scenario: Non-admin user
- **WHEN** a non-admin user sends `GET /api/llm/transcription-models`
- **THEN** the backend returns HTTP 403

### Requirement: Transcription function in llm.py

The `llm.py` module SHALL expose an async `transcribe_audio(file, session)` function that uses the existing OpenAI client to call `client.audio.transcriptions.create()`. The function SHALL read the `transcription_model` setting from the database. If the setting does not exist, the function SHALL raise a `ValueError`. The function SHALL return the transcript text as a string.

#### Scenario: transcribe_audio returns text
- **WHEN** `transcribe_audio()` is called with a valid audio file and a `transcription_model` setting exists
- **THEN** it returns the transcript text string from the API response

#### Scenario: transcribe_audio with no model configured
- **WHEN** `transcribe_audio()` is called and no `transcription_model` setting exists
- **THEN** it raises a `ValueError`
