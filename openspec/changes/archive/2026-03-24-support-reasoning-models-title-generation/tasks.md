## 1. Database Schema

- [x] 1.1 Create Alembic migration for `model_metadata_cache` table (id, normalized_name unique, supports_reasoning bool, max_output_tokens int nullable, source_keys JSON, updated_at datetime)
- [x] 1.2 Add `ModelMetadataCache` SQLAlchemy model to `errand/models.py`

## 2. Model Name Normalization and Lookup

- [x] 2.1 Implement `normalize_model_name()` function — strip provider prefix, colon tags, @ suffixes, lowercase
- [x] 2.2 Implement `lookup_model_metadata(model_name, session)` — two-pass lookup (exact then prefix match) returning `{supports_reasoning, max_output_tokens}` or nulls
- [x] 2.3 Write tests for normalization (ollama-style, provider-prefixed, deep paths, vertex @ style, plain names)
- [x] 2.4 Write tests for lookup (exact match, prefix match, no match, reasoning flag aggregation)

## 3. Registry Fetch and Index Build

- [x] 3.1 Implement `refresh_model_metadata_cache(session)` — fetch LiteLLM JSON from GitHub, parse, normalize, aggregate, upsert into DB
- [x] 3.2 Write tests for registry fetch (successful parse, network error, invalid JSON, reasoning aggregation across providers, conservative max_output_tokens)

## 4. Background Refresh Scheduling

- [x] 4.1 Add startup check — if cache is empty or stale (>7 days), trigger refresh
- [x] 4.2 Add periodic background task for weekly refresh (same pattern as existing background tasks in server lifecycle)
- [x] 4.3 Add on-demand refresh trigger from model list endpoint — fire-and-forget async refresh when unmatched models detected, debounced to 1 hour

## 5. Enriched Model List Endpoint

- [x] 5.1 Modify `GET /api/llm/providers/{id}/models` to return objects `{id, supports_reasoning, max_output_tokens}` instead of plain strings
- [x] 5.2 For each model in the list, look up metadata from cache and attach (null if no match)
- [x] 5.3 If any models are unmatched and cache is stale (>1 hour), trigger background refresh
- [x] 5.4 Write tests for enriched endpoint response format and metadata attachment

## 6. Dynamic max_tokens in generate_title

- [x] 6.1 Modify `generate_title()` to look up model metadata before making the LLM call
- [x] 6.2 Use cached `max_output_tokens` as `max_tokens` parameter, falling back to 300 if no match
- [x] 6.3 After LLM response, detect empty content + non-empty `reasoning_content` and log warning
- [x] 6.4 Write tests for dynamic max_tokens (cached value used, default fallback, reasoning detection warning)

## 7. Frontend Reasoning Warning

- [x] 7.1 Update model selector component to handle enriched model objects (parse `id` for display, store full object for metadata)
- [x] 7.2 Add inline amber warning below model selector when `supports_reasoning: true` is selected for Title Generation or Task Processing roles
- [x] 7.3 Ensure no warning shown for `supports_reasoning: false` or `null`
- [x] 7.4 Write frontend tests for warning display logic
