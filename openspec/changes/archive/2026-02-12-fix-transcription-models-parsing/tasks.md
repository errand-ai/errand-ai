## 1. Fix endpoint parsing

- [x] 1.1 Update `list_transcription_models` in `backend/main.py` to parse `data["data"]` as a list of objects, extracting `model_name` and `model_info` from each entry
- [x] 1.2 Move the parsing logic inside the existing try/except block so unparseable responses return HTTP 502
- [x] 1.3 Add `Authorization: Bearer {OPENAI_API_KEY}` header to the httpx request (discovered during E2E testing — LiteLLM's `/model/info` requires authentication)

## 2. Fix transcribe_audio UploadFile handling

- [x] 2.1 Fix `transcribe_audio` in `backend/llm.py` to read bytes from the UploadFile and pass a `(filename, content, content_type)` tuple to the OpenAI SDK instead of the raw UploadFile object (which the SDK cannot consume)
- [x] 2.2 Add `logger.exception()` to the transcribe endpoint's catch-all handler in `backend/main.py` so errors are visible in logs
- [x] 2.3 Move `logger = logging.getLogger(__name__)` to the top of `backend/main.py`

## 3. Fix test mocks

- [x] 3.1 Update `test_transcription_models_success` mock response to use the list-of-objects format with `model_name` fields
- [x] 3.2 Update `test_transcription_models_empty_list` mock response to use the list-of-objects format
- [x] 3.3 Update `test_transcribe_audio_success` to use a mock UploadFile with async `read()` and assert the SDK receives a `(filename, bytes, content_type)` tuple
- [x] 3.4 Run all tests and verify they pass (212 backend + 180 frontend)
