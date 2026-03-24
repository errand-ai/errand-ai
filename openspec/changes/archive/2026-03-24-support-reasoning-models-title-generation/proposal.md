## Why

Reasoning models (e.g. deepseek-r1, qwen3 in thinking mode, phi-4-reasoning) return their chain-of-thought in a `reasoning_content` field with an empty `content` field. The current `generate_title` function reads only `content`, sees an empty string, and falls back to a truncated title — silently failing for any reasoning model. Additionally, `max_tokens=300` is far too low for reasoning models that burn tokens on thinking before producing output. Users experimenting with local models via Ollama have no way to know which models will work and which won't.

## What Changes

- **Model metadata registry cache**: Fetch LiteLLM's public `model_prices_and_context_window.json` registry, parse it, and cache a normalized lookup index in the database. The index maps model base names to `supports_reasoning` (boolean) and `max_output_tokens` (integer). Refresh weekly, plus on-demand when unmatched models are detected.
- **Fuzzy model name matching**: Normalize model names by stripping provider prefixes, Ollama-style tags (`:8b`, `:latest`), and version suffixes to match local model names (e.g. `deepseek-r1:8b`) against cloud registry entries (e.g. `deepseek/deepseek-r1`).
- **Enriched model list endpoint**: The existing `GET /api/llm/providers/{id}/models` endpoint returns enriched objects instead of plain strings, including `supports_reasoning` and `max_output_tokens` from the cache (or `null` if unmatched).
- **Frontend reasoning warning**: When a user selects a model flagged as `supports_reasoning` for the title generation role, the settings UI displays a warning that reasoning models may be slower and less reliable for structured output tasks.
- **Dynamic max_tokens in generate_title**: Use the cached `max_output_tokens` for the configured model instead of the hardcoded 300. Fall back to current default when no metadata is available.
- **Reasoning response detection**: After an LLM call, if `content` is empty but `reasoning_content` is present, log a clear warning identifying the model as a reasoning model that may not be suitable for structured output tasks.

## Capabilities

### New Capabilities
- `model-metadata-registry`: Fetching, caching, normalizing, and looking up model metadata from the LiteLLM public registry. Covers the DB schema, refresh logic, fuzzy matching algorithm, and lookup API.

### Modified Capabilities
- `llm-integration`: `generate_title` uses cached `max_output_tokens` instead of hardcoded 300, and detects empty content with reasoning_content present.
- `llm-provider-settings-ui`: Model dropdown returns enriched objects with metadata; frontend shows reasoning model warning.

## Impact

- **Backend**: New DB table for model metadata cache. New background task for registry refresh. Modified `generate_title` in `errand/llm.py`. Modified `list_provider_models` in `errand/main.py`.
- **Frontend**: Modified model selector component in Task Management settings to handle enriched model objects and display warnings.
- **Database**: New Alembic migration for the model metadata cache table.
- **External dependency**: Periodic HTTP fetch of `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` (~2MB).
