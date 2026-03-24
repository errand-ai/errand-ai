## Context

The `generate_title` function in `errand/llm.py` calls an LLM to classify and title new tasks. It sends `max_tokens=300` and reads `response.choices[0].message.content`. Reasoning models (deepseek-r1, qwen3 in thinking mode, phi-4-reasoning) put their chain-of-thought in `reasoning_content` and leave `content` empty — or exhaust the 300-token budget on thinking and never produce output. The function sees empty content and falls back to a truncated title, silently failing.

Users are increasingly running local models via Ollama/LiteLLM and have no visibility into which models will work for structured output tasks. The OpenAI-compatible `/v1/models` endpoint provides no capability metadata.

LiteLLM maintains a public JSON registry (`model_prices_and_context_window.json`) with 2,594 models including `supports_reasoning` and `max_output_tokens` fields. This registry covers cloud providers well but has limited ollama entries. However, local model names (e.g. `deepseek-r1:8b`) can be fuzzy-matched against cloud equivalents (e.g. `deepseek/deepseek-r1`) to extract metadata.

## Goals / Non-Goals

**Goals:**
- Make `generate_title` work correctly with reasoning models by using appropriate `max_tokens`
- Give users visibility when they select a reasoning model for title generation
- Cache model metadata in the database for fast lookups without blocking model selection
- Handle unknown models gracefully (no match = use defaults, not an error)

**Non-Goals:**
- Supporting non-OpenAI-compatible API endpoints (e.g. Ollama's native `/api/show`)
- Filtering or blocking reasoning models from selection — users should be warned, not restricted
- Real-time inference probing to detect model capabilities
- Caching the full registry JSON — only the normalized lookup index is stored

## Decisions

### 1. Use LiteLLM's public registry as the metadata source

**Decision**: Fetch `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` and build a normalized lookup index.

**Why**: It's free, no auth required, covers 2,594 models with exactly the fields we need (`supports_reasoning`, `max_output_tokens`). No other public registry offers comparable coverage without authentication (OpenRouter requires an API key).

**Alternatives considered**:
- Ollama's `/api/show` endpoint — returns `capabilities` array with `"thinking"` flag, but it's a non-OpenAI-compatible endpoint and only works for Ollama. We don't want to support provider-specific APIs.
- HuggingFace `config.json` per model — has `max_position_embeddings` but no reasoning flag, and requires knowing the exact HF repo name.
- LiteLLM's `/model/info` proxy endpoint — only returns metadata for models configured in the user's LiteLLM instance, not the full registry. Ollama models won't have `supports_reasoning` unless manually configured.

### 2. Two-pass fuzzy matching for model name lookup

**Decision**: Normalize model names by stripping provider prefixes, colon tags, and `@` suffixes. First try exact match on normalized name, then prefix match as fallback.

Normalization: `ollama/deepseek-r1:8b` → take last path segment → `deepseek-r1:8b` → strip colon tag → `deepseek-r1` → lowercase.

- **Pass 1 (exact)**: Look up `deepseek-r1` directly in the index. High confidence.
- **Pass 2 (prefix)**: If no exact match, find entries where the normalized name is a prefix (e.g. `qwen3` matches `qwen3-30b-a3b`, `qwen3-coder-flash`). Medium confidence. If any prefix-matched entry has `supports_reasoning=true`, the model is flagged as reasoning.

**Why**: Local model names don't match registry keys exactly, but the base model family name is almost always a prefix or exact match after normalization. Testing against common ollama names shows this catches deepseek-r1, qwen3, phi-4-reasoning, magistral, and others correctly. False negatives (no match) are safe — we just use defaults. False positives for reasoning (e.g. qwen3 flagged because some variants support thinking) err on the safe side — a warning and higher max_tokens are harmless for non-reasoning models.

### 3. Store normalized index in DB, not the raw JSON

**Decision**: Parse the ~2MB JSON into a `model_metadata_cache` table with columns: `normalized_name`, `supports_reasoning`, `max_output_tokens`, `source_keys` (JSON array of original registry keys that mapped to this entry), `updated_at`.

**Why**: The raw JSON is large and has 2,594 entries with many duplicates per base model (different providers). The normalized index deduplicates to ~500-800 unique base names, making lookups fast and storage minimal. Storing in the DB means it persists across restarts.

### 4. Weekly refresh + on-demand for unmatched models

**Decision**: Refresh the registry cache weekly via a background task. Additionally, when the model list endpoint serves a response containing unmatched models, trigger an async background refresh (don't block the response).

**Why**: The registry changes frequently as new models are added. Weekly keeps it reasonably fresh. On-demand refresh handles the case where a user pulls a new ollama model that was recently added to the registry — next time they open the dropdown, the refresh is triggered and available for subsequent requests.

### 5. Use cached max_output_tokens as max_tokens in generate_title

**Decision**: When calling the LLM, look up the model in the metadata cache and use its `max_output_tokens` as the `max_tokens` parameter. If no match, fall back to the current default (300).

**Why**: The user has already chosen this model and been warned if it's a reasoning model. Using the model's actual max output capacity gives reasoning models enough room to think and produce output. For non-reasoning models, the value is typically 4096-8192, which is fine — the model will stop at `finish_reason=stop` well before exhausting the budget. Ollama silently clamps if the value exceeds its internal limit, and cloud models have context windows large enough that our small prompt + max_output_tokens won't overflow.

### 6. Enrich existing model list endpoint response

**Decision**: Change `GET /api/llm/providers/{id}/models` to return objects `{id, supports_reasoning, max_output_tokens}` instead of plain strings. The frontend already calls this endpoint to populate the dropdown.

**Why**: No new endpoints needed. The frontend gets metadata in the same call it already makes. `supports_reasoning` and `max_output_tokens` can be `null` for unmatched models — the frontend treats null as "unknown" and shows no warning.

## Risks / Trade-offs

- **Registry availability**: If GitHub raw URL is unreachable, the cache won't refresh. → Mitigation: Cache persists in DB, so stale data is used. Log warning on fetch failure. Never block on refresh.
- **Fuzzy matching false positives**: Prefix matching could flag a non-reasoning model as reasoning (e.g. if a model family has both reasoning and non-reasoning variants). → Mitigation: The consequence is just a warning and higher max_tokens, both harmless for non-reasoning models.
- **Fuzzy matching false negatives**: A model with an unusual name won't match. → Mitigation: Falls back to defaults (300 max_tokens, no warning). The existing behavior — same as before this change.
- **Registry doesn't cover all local models**: Only 29 ollama entries currently. → Mitigation: Fuzzy matching bridges this gap by matching against cloud equivalents. Models with no cloud equivalent at all are edge cases that get default behavior.
- **Breaking API change**: Model list endpoint changes from string array to object array. → Mitigation: Frontend and backend are deployed together from the same Docker image. No external consumers of this endpoint.
