## Context

The task runner uses the OpenAI Agent SDK to execute agents. The SDK's `MultiProvider` class splits model names on `/` to extract a provider prefix (e.g. `litellm/`, `openai/`). Only `litellm` and `openai` are recognized prefixes — anything else raises `UserError("Unknown prefix: ...")`.

The task runner always communicates with LiteLLM as its OpenAI-compatible backend (configured via `OPENAI_BASE_URL`). However, it passes the raw model name (e.g. `bedrock/gpt-oss:20b`) directly to the `Agent()` constructor, causing the SDK to misinterpret `bedrock` as a provider prefix.

## Goals / Non-Goals

**Goals:**
- Model names containing slashes work correctly in the task runner
- All models route through the SDK's `LitellmProvider`, which passes the model name through to the configured OpenAI-compatible endpoint without modification

**Non-Goals:**
- Supporting the SDK's native OpenAI provider (we always use LiteLLM)
- Changing how `OPENAI_MODEL` is set by the task manager

## Decisions

**Use `OpenAIProvider` directly instead of `MultiProvider`**: In `main.py`, set `model_provider=OpenAIProvider()` on the `RunConfig` to bypass the SDK's `MultiProvider` entirely. `MultiProvider` splits model names on `/` to extract provider prefixes (e.g. `litellm/`, `openai/`), which causes model names like `bedrock/gpt-oss:20b` to be misinterpreted. `OpenAIProvider` passes model names through to the configured OpenAI client as-is, which is exactly what we need since the client already points at LiteLLM.

This is the correct approach because:
1. The task runner exclusively uses LiteLLM via `set_default_openai_client()` — all models go through the same OpenAI-compatible endpoint regardless of name format
2. `OpenAIProvider` doesn't parse model names — it passes them directly to the API client, so slashes in model names (e.g. `bedrock/gpt-oss:20b`) work correctly
3. No new package dependencies — unlike the original `litellm/` prefix approach which would require the `litellm` Python package (not installed in the task-runner container)
4. No changes needed in the task manager or anywhere upstream

## Risks / Trade-offs

- **Bypasses MultiProvider routing**: If the task runner ever needs to use multiple LLM providers (not just LiteLLM), this approach would need to be revisited. Currently, all models route through a single LiteLLM proxy, so MultiProvider routing is unnecessary.
- **OpenAI SDK format**: The model name is sent as-is to the OpenAI-compatible API. LiteLLM handles provider-specific routing (e.g. `bedrock/` prefix) on the server side.
