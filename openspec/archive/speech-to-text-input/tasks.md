## 1. Backend transcription function

- [x] 1.1 Add `transcribe_audio(file, session)` async function to `llm.py`: reads `transcription_model` setting from DB, raises `ValueError` if not set, calls `client.audio.transcriptions.create(model=model, file=file)`, returns the transcript text string
- [x] 1.2 Handle missing LLM client: if `get_llm_client()` returns None, raise an appropriate exception that the endpoint can catch

## 2. Backend transcription endpoint

- [x] 2.1 Add `POST /api/transcribe` endpoint in `main.py`: accepts `file: UploadFile`, calls `transcribe_audio()`, returns `{"text": "..."}` with HTTP 200
- [x] 2.2 Apply `get_current_user` dependency (or `require_editor` if rbac-and-task-lifecycle has landed)
- [x] 2.3 Error handling: return 503 if transcription not configured (no model selected) or LLM client missing, 502 if transcription API call fails

## 3. Backend transcription status endpoint

- [x] 3.1 Add `GET /api/transcribe/status` endpoint in `main.py` using `get_current_user` dependency: check if `transcription_model` setting exists in DB and LLM client is configured, return `{"enabled": true/false}`

## 4. Backend transcription models endpoint

- [x] 4.1 Add `GET /api/llm/transcription-models` endpoint in `main.py` using `require_admin` dependency: derive LiteLLM base URL from `OPENAI_BASE_URL` (strip `/v1` suffix), call `/model/info` via `httpx`, filter results by `mode == "audio_transcription"`, return sorted JSON array of model ID strings
- [x] 4.2 Error handling: return 502 if the `/model/info` request fails, return empty array if no transcription models found

## 5. Frontend voice input component

- [x] 5.1 Add microphone recording logic to `TaskForm.vue`: use `navigator.mediaDevices.getUserMedia()` to request microphone access, create a `MediaRecorder` instance, collect audio chunks via `ondataavailable`, produce a `Blob` on stop
- [x] 5.2 Add microphone button UI: icon button between text input and "Add Task" button, conditionally rendered only when `MediaRecorder` is supported AND transcription is enabled (check `GET /api/transcribe/status` on component mount)
- [x] 5.3 Add recording state UI: button turns red with pulsing animation while recording, displays elapsed time counter, shows loading spinner during transcription
- [x] 5.4 Handle microphone permission denied: display error message "Microphone access is required for voice input"

## 6. Frontend transcription integration

- [x] 6.1 On recording stop, send the audio blob to `POST /api/transcribe` as multipart form data (field name `file`), using the auth store token for the Authorization header
- [x] 6.2 On successful response, append the transcript text to the existing text input value (with space separator if input is non-empty), focus the input
- [x] 6.3 On error, display message below the form: "Voice transcription failed. Please try again or type your task."

## 7. Settings page: Transcription model

- [x] 7.1 Add "Transcription Model" dropdown to the "LLM Models" section on the Settings page, populated from `GET /api/llm/transcription-models` (filtered list), loading current value from `transcription_model` setting
- [x] 7.2 Show placeholder "Select a model to enable voice input" when no model is selected; include a "Disabled" option that sends `{"transcription_model": null}` to remove the setting
- [x] 7.3 Handle empty model list (dropdown disabled with "No transcription models available") and endpoint failure (dropdown disabled with error message)

## 8. Backend tests

- [x] 8.1 Test `transcribe_audio`: mock the OpenAI client, verify it calls `audio.transcriptions.create` with correct model and file, returns transcript text; verify it raises `ValueError` when no `transcription_model` setting exists
- [x] 8.2 Test `POST /api/transcribe`: successful transcription returns 200 with text, no model configured returns 503, missing LLM client returns 503, transcription failure returns 502, unauthenticated returns 401
- [x] 8.3 Test `GET /api/transcribe/status`: returns `{"enabled": true}` when model setting exists and LLM client configured, returns `{"enabled": false}` when either is missing
- [x] 8.4 Test `GET /api/llm/transcription-models`: mock the `/model/info` response, verify filtering by `mode == "audio_transcription"`, verify sorted output, verify 403 for non-admin, verify 502 when proxy unreachable

## 9. Frontend tests

- [x] 9.1 Test TaskForm renders microphone button when MediaRecorder is available AND transcription status is enabled; hides it when either condition is false
- [x] 9.2 Test recording flow: clicking mic button starts recording (state change), clicking again stops and triggers transcription API call
- [x] 9.3 Test transcript insertion: successful transcription appends text to input, error shows error message
- [x] 9.4 Test Settings page renders "Transcription Model" dropdown with filtered models, shows placeholder when no model selected, shows "Disabled" option

## 10. Version bump and verification

- [x] 10.1 Bump VERSION file (minor increment)
- [x] 10.2 Run full backend and frontend test suites and verify all tests pass
