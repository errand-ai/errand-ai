## MODIFIED Requirements

### Requirement: Transcription endpoint

The backend SHALL expose `POST /api/transcribe` requiring an authenticated user. The endpoint SHALL accept a multipart file upload with field name `file`. The endpoint SHALL check that a `transcription_model` setting exists in the database and contains a valid `{"provider_id": "<uuid>", "model": "<model-id>"}` value. If the setting is empty, has a null `provider_id`, or references a non-existent provider, the endpoint SHALL return HTTP 503 with `{"detail": "Transcription not configured"}`. Otherwise, the endpoint SHALL resolve the provider's `AsyncOpenAI` client via the client pool and forward the audio file using `client.audio.transcriptions.create()` with the configured model. The endpoint SHALL return a JSON object `{"text": "<transcript>"}` with HTTP 200.

#### Scenario: Successful transcription
- **WHEN** an authenticated user sends `POST /api/transcribe` with a valid audio file and `transcription_model` contains a valid provider and model
- **THEN** the backend resolves the provider client and returns HTTP 200 with `{"text": "Schedule a meeting with the team"}`

#### Scenario: Transcription not configured (empty setting)
- **WHEN** a user sends `POST /api/transcribe` and `transcription_model` is empty or has null provider_id
- **THEN** the backend returns HTTP 503 with `{"detail": "Transcription not configured"}`

#### Scenario: Transcription provider deleted
- **WHEN** a user sends `POST /api/transcribe` and `transcription_model` references a provider that no longer exists
- **THEN** the backend returns HTTP 503 with `{"detail": "Transcription not configured"}`

#### Scenario: Transcription API failure
- **WHEN** the provider returns an error during transcription
- **THEN** the backend returns HTTP 502 with `{"detail": "Transcription failed"}`

### Requirement: Transcription status endpoint

The backend SHALL expose `GET /api/transcribe/status` requiring any authenticated user. The endpoint SHALL check whether a `transcription_model` setting exists with a valid `provider_id` that references an existing provider in the `llm_provider` table. The endpoint SHALL return `{"enabled": true}` if the provider exists and the model is set, and `{"enabled": false}` otherwise.

#### Scenario: Transcription enabled
- **WHEN** `transcription_model` contains a valid provider_id and model
- **THEN** `GET /api/transcribe/status` returns `{"enabled": true}`

#### Scenario: Transcription not configured
- **WHEN** `transcription_model` is empty or references a deleted provider
- **THEN** `GET /api/transcribe/status` returns `{"enabled": false}`

### Requirement: Transcription models endpoint

The backend SHALL remove the `GET /api/llm/transcription-models` endpoint. Transcription model listing is now handled by `GET /api/llm/providers/{id}/models?mode=audio_transcription` (defined in the `llm-providers` spec).

#### Scenario: Legacy endpoint removed
- **WHEN** a client sends `GET /api/llm/transcription-models`
- **THEN** the backend returns HTTP 404 (endpoint does not exist)

### Requirement: Transcription function in llm.py

The `llm.py` module SHALL expose an async `transcribe_audio(file, session)` function that reads the `transcription_model` setting, resolves the provider_id to an `AsyncOpenAI` client via the client pool, and calls `client.audio.transcriptions.create()` with the configured model. If the setting is empty or the provider does not exist, the function SHALL raise a `ValueError`.

#### Scenario: transcribe_audio resolves provider client
- **WHEN** `transcribe_audio()` is called and `transcription_model` is `{"provider_id": "uuid-1", "model": "whisper-1"}`
- **THEN** it resolves provider "uuid-1", creates/reuses a client, and calls transcription with model "whisper-1"

#### Scenario: transcribe_audio with no model configured
- **WHEN** `transcribe_audio()` is called and `transcription_model` is empty
- **THEN** it raises a `ValueError`

## REMOVED Requirements

### Requirement: Transcription error handling
**Reason**: The "LLM client not configured" scenario (checking `OPENAI_BASE_URL`) is replaced by provider-based resolution. The 503 response for unconfigured transcription is now covered by the modified transcription endpoint requirement above.
**Migration**: Error handling for missing providers is now part of the provider-scoped client resolution.
