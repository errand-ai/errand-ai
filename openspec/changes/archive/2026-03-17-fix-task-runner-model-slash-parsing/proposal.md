## Why

The task runner crashes with `"ERROR Agent execution failed: Unknown prefix: bedrock"` when the configured model name contains a slash (e.g. `bedrock/gpt-oss:20b`). The OpenAI Agent SDK's `MultiProvider` interprets slashes as prefix separators (e.g. `litellm/` or `openai/`), so a model name like `bedrock/gpt-oss:20b` is parsed as prefix `bedrock` with model `gpt-oss:20b`, which fails because `bedrock` is not a recognized provider prefix. Since the task runner always uses LiteLLM as its backend, all models should be routed through the SDK's `LitellmProvider`.

## What Changes

- Prefix the model name with `litellm/` in the task runner before passing it to the Agent SDK, so the SDK routes through its `LitellmProvider` instead of trying to parse slashes in the model name as provider prefixes
- Update tests to cover model names containing slashes

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `task-runner-agent`: The model name handling changes — the task runner must prefix all models with `litellm/` to ensure correct SDK routing

## Impact

- **Code**: `task-runner/main.py` — model name passed to `Agent()` constructor
- **Tests**: `task-runner/test_main.py` — add/update test for slash-containing model names
- **No API or schema changes** — the `OPENAI_MODEL` env var still accepts raw model names; the prefixing is internal
