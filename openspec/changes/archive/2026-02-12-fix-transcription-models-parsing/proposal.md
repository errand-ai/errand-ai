## Why

The `GET /api/llm/transcription-models` endpoint fails with "Failed to load transcription models" when models with `mode: audio_transcription` are configured in LiteLLM. The endpoint parses the LiteLLM `/model/info` response as a dict keyed by model name, but LiteLLM actually returns `data` as a list of objects. Calling `.items()` on a list raises `AttributeError`, causing an unhandled 500 error. The existing tests pass because they mock the response in the wrong shape (dict instead of list).

## What Changes

- Fix `list_transcription_models` in `backend/main.py` to handle the LiteLLM `/model/info` list response format: iterate over the list and extract `model_name` and `model_info` from each object
- Update test mocks in `backend/tests/test_transcription.py` to use the real LiteLLM response shape (list of objects with `model_name` field)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `transcription-api`: The transcription models endpoint spec needs to document the expected LiteLLM response format (list of objects) and clarify the parsing behaviour

## Impact

- **Backend**: `main.py` — `list_transcription_models` endpoint parsing logic
- **Tests**: `tests/test_transcription.py` — mock response shapes for transcription model tests
- **No frontend changes**: The API contract (returns sorted array of model ID strings) stays the same
