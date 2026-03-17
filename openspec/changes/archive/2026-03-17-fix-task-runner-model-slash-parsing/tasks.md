## 1. Fix model name routing

- [x] 1.1 In `task-runner/main.py`, set `model_provider=OpenAIProvider()` on `RunConfig` to bypass `MultiProvider`'s slash-based prefix parsing (replaces original plan of `litellm/` prefix which required the `litellm` package)
- [x] 1.2 The `Agent()` constructor uses the raw `env["OPENAI_MODEL"]` — no prefix manipulation needed since `OpenAIProvider` passes model names through as-is

## 2. Tests

- [x] 2.1 Add test cases for model names with slashes: plain model name (`gpt-4o`), model with slash (`bedrock/gpt-oss:20b`), Bedrock Claude model name resolution
- [x] 2.2 Verify model names with slashes are handled correctly in token resolution and agent configuration
