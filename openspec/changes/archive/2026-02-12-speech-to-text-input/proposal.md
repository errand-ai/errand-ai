## Why

Creating a task currently requires typing out the description, which can be slow and inconvenient — especially on mobile or when the user wants to quickly capture an idea. Adding speech-to-text voice input lets users describe a task verbally, lowering the friction for task capture.

## What Changes

- **Microphone button on task creation form**: A new "record" button next to the existing text input. Press to start recording, press again (or release) to stop. The audio is transcribed and inserted into the input field.
- **Backend transcription endpoint**: A new `POST /api/transcribe` endpoint that accepts an audio file and returns the transcript text. The endpoint proxies the audio through the existing LiteLLM proxy to its `/v1/audio/transcriptions` endpoint.
- **LiteLLM proxy configuration**: Add a transcription model to the LiteLLM config (Groq Whisper Large v3 or OpenAI whisper-1). No new external service — reuses the existing LLM infrastructure.
- **Transcription model setting**: Add a "Transcription Model" dropdown to the Settings page, filtered to only show models with audio transcription capability. If no transcription model is selected, the voice input feature is disabled and the microphone button is hidden.
- **Transcription status endpoint**: A new `GET /api/transcribe/status` endpoint that returns whether transcription is enabled, allowing the frontend to conditionally show the microphone button without requiring admin-level settings access.

## Research Summary

### Architecture: Record-Then-Transcribe via LiteLLM Proxy (Recommended)

We evaluated five architectural patterns and six STT providers. The recommended approach is **Pattern A: Record-Then-Transcribe** using the browser's `MediaRecorder` API to capture audio, then sending it to the backend for transcription via the existing LiteLLM proxy.

**Why this pattern wins:**

| Criterion | Record-Then-Transcribe | Web Speech API | Client-Side WASM | Real-Time Streaming |
|-----------|----------------------|----------------|-----------------|-------------------|
| Browser support | 97%+ (MediaRecorder) | Chrome + Safari only (no Firefox) | Modern + SIMD | 97%+ (WebSocket) |
| Integration effort | Low (LiteLLM already supports it) | Very low | Medium-High (75-142MB model download, COOP/COEP headers) | High (WebSocket management) |
| Privacy | Audio through our backend | Audio to Google/Apple | Fully local | Audio through our backend |
| Cost | ~$0.002-0.006/min | Free | Free | $0.06+/min (OpenAI Realtime) |
| Latency | 1-3s for short clips | Real-time | 20-30s per minute of audio | Real-time |

**Provider comparison (all LiteLLM-compatible):**

| Provider | Price/min | Speed | Accuracy | Notes |
|----------|-----------|-------|----------|-------|
| **Groq Whisper Large v3** | ~$0.002 | 164x real-time (<1s) | Very good | Cheapest, fastest |
| OpenAI whisper-1 | $0.006 | 1-3s for short clips | Very good | Most reliable |
| OpenAI gpt-4o-mini-transcribe | $0.003 | Similar | Better than whisper-1 | Newer model |
| Deepgram Nova-3 | $0.004-0.008 | <300ms streaming | Excellent (5.26% WER) | Best for streaming |

For a task manager where users dictate 5-30 second descriptions, the 1-3 second transcription latency is imperceptible. At 100 transcriptions/day of 15 seconds each (~25 min/day), cost is ~$0.05/day with Groq.

**Alternatives considered and rejected:**
- **Web Speech API**: No Firefox support, audio goes to browser vendor cloud (no privacy control), not standardised
- **Client-side WASM (Whisper.cpp)**: 75-142MB model download, 20-30s latency per minute of audio, requires COOP/COEP headers that can break other integrations
- **Real-time streaming (WebSocket)**: Significantly more complex, 10-30x more expensive (OpenAI Realtime API), overkill for short voice inputs

**AWS Bedrock — not suitable:**
AWS Bedrock does not offer a suitable speech-to-text transcription model for this use case. Amazon Nova Sonic (v1 and v2) is a speech-to-speech conversational AI model requiring a bidirectional streaming API (`InvokeModelWithBidirectionalStream`) — it is not a file-based transcription service and LiteLLM does not support it. Amazon Transcribe is a separate AWS service (not available through Bedrock) and is also not supported by LiteLLM. The recommended LiteLLM-compatible transcription providers are: OpenAI Whisper, Groq Whisper, Deepgram, Azure Whisper, Fireworks AI, Vertex AI, and Gemini.

## Capabilities

### New Capabilities

- `voice-input`: Microphone recording UI on task creation form, audio capture via MediaRecorder API, transcription result insertion into text input
- `transcription-api`: Backend `POST /api/transcribe` endpoint, audio forwarding to LiteLLM proxy, response handling

### Modified Capabilities

- `admin-settings-ui`: Add "Transcription Model" dropdown to Settings page, filtered to only show models with transcription capability
- `admin-settings-api`: New `GET /api/llm/transcription-models` endpoint that queries LiteLLM's `/model/info` and filters by `mode: audio_transcription`
- `kanban-frontend`: Task creation form gains a microphone button alongside the text input

## Impact

- `backend/main.py`: New `POST /api/transcribe` endpoint, new `GET /api/transcribe/status` endpoint, new `GET /api/llm/transcription-models` endpoint
- `backend/llm.py`: Add transcription function using OpenAI SDK's `client.audio.transcriptions.create()`
- `frontend/src/pages/KanbanBoard.vue` (or task form component): Microphone button (conditionally shown), MediaRecorder integration, recording state UI
- `frontend/src/pages/SettingsPage.vue`: New "Transcription Model" dropdown in LLM Models section with filtered model list
- LiteLLM proxy config: Add transcription model entry with `model_info.mode: audio_transcription`
- No database migration — uses existing settings table for model selection
