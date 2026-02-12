## Context

The `list_transcription_models` endpoint in `backend/main.py` queries LiteLLM's `/model/info` endpoint and filters for models with `mode: audio_transcription`. The current code treats the `data` field as a dict (`data.get("data", {}).items()`), but LiteLLM returns it as a list:

```json
{
  "data": [
    {
      "model_name": "groq/whisper-large-v3",
      "model_info": { "mode": "audio_transcription", ... },
      "litellm_params": { ... }
    },
    {
      "model_name": "gpt-4o",
      "model_info": { "mode": "chat", ... },
      "litellm_params": { ... }
    }
  ]
}
```

Calling `.items()` on this list raises `AttributeError`, which is not caught by the try/except (that only wraps the HTTP call), resulting in an unhandled 500 error.

## Goals / Non-Goals

**Goals:**
- Fix the parsing to handle LiteLLM's actual list-of-objects response format
- Update test mocks to reflect the real response shape
- Maintain the same API contract: endpoint returns a sorted JSON array of model ID strings

**Non-Goals:**
- Supporting both dict and list formats (the dict format was never correct)
- Changing the frontend — the API response shape is unchanged
- Adding caching or performance improvements to the model info call

## Decisions

### 1. Parse `data` as a list, extract `model_name`

**Decision**: Iterate over `data.get("data", [])` as a list, reading `item.get("model_name")` and `item.get("model_info", {})` from each entry.

**Alternative**: Support both dict and list formats with a type check. Rejected — the dict format was never the real API shape, just a test artefact.

### 2. Wrap parsing in the existing try/except

**Decision**: Move the parsing logic inside the existing try/except block so any unexpected response shape returns a clean 502 instead of a 500.

### 3. Update test mocks to list format

**Decision**: Change the mock response in all transcription model tests from the dict format to the list-of-objects format matching the real LiteLLM API.

## Risks / Trade-offs

- **[LiteLLM API stability]** The `/model/info` endpoint format could change in future LiteLLM versions. → The parsing is already defensive with `.get()` defaults; wrapping it in try/except provides a safety net.
- **[No integration test]** We can't easily test against a real LiteLLM instance in CI. → The fix corrects the mock shape to match reality, which is the best we can do in unit tests.
