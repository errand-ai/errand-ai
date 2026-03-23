## Why

When users create tasks with scheduling language (e.g. "In two hours, publish one of the approved tweets"), the system correctly extracts timing information but saves the raw input as the task description. This means the description contains redundant scheduling references that the agent doesn't need — the scheduling is already captured in `execute_at`/`repeat_interval` fields. The description should only contain what the agent needs to do, not when.

## What Changes

- The LLM prompt in `generate_title` adds a `description` field to the JSON response — the task description with all scheduling/timing references removed
- `LLMResult` gains a `description` field to carry the cleaned description
- Task creation uses the LLM-cleaned description instead of raw input
- When the LLM cannot extract a meaningful description (e.g. input is purely scheduling like "remind me in 2 hours"), the task is created with scheduling info but placed in `review` status with "Needs Info" tag so the user can add a proper description

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `llm-integration`: LLM response JSON schema gains a `description` field; prompt instructs model to strip timing references from description
- `task-categorisation`: When LLM returns empty/null description, task gets "Needs Info" tag and routes to `review` status

## Impact

- `errand/llm.py`: `LLMResult` dataclass, `generate_title` prompt, `_parse_llm_response` parser
- `errand/main.py`: Task creation endpoint uses `llm_result.description` with fallback
- `errand/tests/test_llm.py`: New test cases for description extraction and empty description handling
- `errand/tests/test_tasks.py`: Updated integration tests for description in created tasks
