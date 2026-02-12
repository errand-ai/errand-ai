## Context

The task creation form (`TaskForm.vue`) is a simple text input + "Add Task" button. When submitted, the backend's `create_task` endpoint processes the input through the LLM (via `generate_title` in `llm.py`) to extract title, category, and scheduling. The LLM integration uses an `AsyncOpenAI` client configured with `OPENAI_BASE_URL` and `OPENAI_API_KEY`, pointing to a LiteLLM proxy. The OpenAI SDK's `client.audio.transcriptions.create()` method is compatible with the LiteLLM proxy's `/v1/audio/transcriptions` endpoint.

LiteLLM's `/model/info` endpoint returns model metadata including a `mode` field that can be `audio_transcription` for transcription-capable models. This is separate from the standard `/v1/models` endpoint which does not include capability metadata.

## Goals / Non-Goals

**Goals:**
- Add a microphone button to the task creation form for voice input
- Transcribe audio on the backend via the existing LiteLLM proxy
- Allow the admin to select the transcription model from a filtered list of transcription-capable models
- Disable voice input entirely if no transcription model is configured
- Keep the text input functional — voice input is additive, not a replacement

**Non-Goals:**
- Real-time streaming transcription (record-then-transcribe is sufficient for short task descriptions)
- Client-side transcription (WASM/WebGPU models add complexity and large downloads)
- Voice commands beyond task creation (e.g. "delete task X")
- Multi-language configuration UI (the STT model handles language detection automatically)
- AWS Bedrock integration (Nova Sonic is speech-to-speech, not transcription; Amazon Transcribe is a separate service not supported by LiteLLM)

## Decisions

### Decision: Record-Then-Transcribe architecture

Use the browser's `MediaRecorder` API to capture audio, send the complete recording to the backend as a file upload, and return the transcript text. No streaming, no WebSocket — simple HTTP POST.

**Rationale:** For task descriptions (5-30 seconds of audio), the 1-3 second transcription latency is negligible. MediaRecorder has 97%+ browser support. This avoids the complexity of WebSocket streaming and keeps the implementation simple.

### Decision: Feature disabled until admin selects a transcription model

The voice input feature is disabled by default. The microphone button is only shown if a `transcription_model` setting exists in the database. The admin must explicitly select a transcription model on the Settings page to enable the feature. There is no default model.

**Rationale:** Transcription incurs per-request costs. The admin should make a deliberate choice about which provider and model to use. This also avoids failures if the LiteLLM proxy has no transcription model configured.

### Decision: Transcription status endpoint for frontend

Add `GET /api/transcribe/status` (any authenticated user) that returns `{"enabled": true/false}`. The frontend calls this on load and conditionally renders the microphone button. This avoids exposing the admin settings to non-admin users.

**Rationale:** The kanban board is used by all roles. The frontend needs to know if transcription is available without reading admin-only settings. A lightweight status check is the simplest approach.

### Decision: Filtered transcription model list

Add `GET /api/llm/transcription-models` (admin only) that queries the LiteLLM proxy's `/model/info` endpoint and returns only models where `mode == "audio_transcription"`. The Settings page uses this endpoint to populate the "Transcription Model" dropdown instead of the generic `/api/llm/models` endpoint.

**Rationale:** The standard `/v1/models` endpoint does not include capability metadata. LiteLLM's `/model/info` endpoint provides the `mode` field. Filtering server-side ensures only transcription-capable models appear in the dropdown, preventing admin misconfiguration.

### Decision: Backend transcription endpoint

Add `POST /api/transcribe` in `main.py` that accepts a multipart file upload. The endpoint uses the existing OpenAI client from `llm.py` to call `client.audio.transcriptions.create()` with the uploaded audio file and the configured transcription model. Returns `{"text": "..."}`.

**Rationale:** Keeps audio processing server-side (privacy control, model flexibility). Reuses the existing LLM client and infrastructure. The OpenAI SDK handles the multipart upload to the LiteLLM proxy.

### Decision: Reuse existing OpenAI client for transcription

The `get_llm_client()` function in `llm.py` already returns an `AsyncOpenAI` client. Add a `transcribe_audio()` function alongside `generate_title()` that uses the same client. The transcription model is read from the `transcription_model` setting. If the setting does not exist, the function raises an error (feature not enabled).

**Rationale:** No new dependencies, no new client initialization. The LiteLLM proxy already supports routing transcription requests — only the proxy config needs a new model entry.

### Decision: Audio format — WebM/Opus

`MediaRecorder` defaults to WebM/Opus in Chrome and Firefox, and MP4/AAC in Safari. The OpenAI transcription API accepts both formats. Send the audio as-is without client-side format conversion.

**Rationale:** Avoids the complexity of client-side audio transcoding. Both common browser formats are accepted by the API. The backend passes the file through without processing.

### Decision: Microphone button with click-to-toggle UX

Add a microphone icon button next to the text input. Click to start recording (button turns red with pulsing animation), click again to stop. On stop, the audio is sent for transcription and the result is appended to the text input (not replaced, in case the user already typed something).

**Rationale:** Click-to-toggle is simpler than hold-to-record (which has poor mobile UX). Appending rather than replacing respects any existing input text.

### Decision: Editor/admin role required for transcription

The `POST /api/transcribe` endpoint requires the `editor` or `admin` role (or `get_current_user` if the rbac-and-task-lifecycle change hasn't landed yet). Viewers cannot create tasks, so they don't need transcription.

**Rationale:** Transcription costs money per request. Aligning with task creation permissions prevents unauthorized use.

## Risks / Trade-offs

- **[Browser microphone permission]** → The browser will prompt the user for microphone access on first use. This is standard UX and cannot be bypassed. The prompt only appears once per origin.
- **[LiteLLM `/model/info` availability]** → The `/model/info` endpoint is LiteLLM-specific (not part of the OpenAI API). The backend calls it via direct HTTP using the same base URL. If the proxy doesn't expose this endpoint, the transcription models list will be empty and the admin cannot enable the feature.
- **[Audio file size]** → MediaRecorder at default quality produces ~12KB/sec (Opus). A 30-second recording is ~360KB. The OpenAI API limit is 25MB. No size issue for task descriptions.
- **[No offline support]** → If the backend or LLM proxy is unreachable, transcription fails. The user can always fall back to typing.
- **[AWS Bedrock not usable]** → Nova Sonic requires a bidirectional streaming API and is designed for conversational AI, not file transcription. Amazon Transcribe is a separate service. Neither is supported by LiteLLM's transcription proxy. If the deployment only has Bedrock access, voice input cannot be enabled.
