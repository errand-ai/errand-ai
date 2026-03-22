## 1. LLM Response Schema

- [x] 1.1 Add `description: str | None = None` field to `LLMResult` dataclass in `errand/llm.py`
- [x] 1.2 Update `generate_title` system prompt to include `description` field in JSON schema — instruct the model to return the task description with all scheduling/timing references removed, containing only what needs to be done
- [x] 1.3 Update `_parse_llm_response` to extract `description` from the LLM JSON response (None if missing or not a string)

## 2. Task Creation Endpoint

- [x] 2.1 Update `main.py` task creation to use `llm_result.description` instead of `input_text` as task description
- [x] 2.2 When LLM succeeds but returns empty/null description, add "Needs Info" tag so task routes to `review` status

## 3. Tests

- [x] 3.1 Add unit tests in `test_llm.py` for `_parse_llm_response` extracting `description` field (present, missing, non-string)
- [x] 3.2 Add unit test for `generate_title` returning cleaned description in `LLMResult`
- [x] 3.3 Add integration test in `test_tasks.py` for task created with cleaned description (scheduled task with timing removed)
- [x] 3.4 Add integration test for empty LLM description routing to review with "Needs Info" tag
