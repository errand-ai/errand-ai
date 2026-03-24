## ADDED Requirements

### Requirement: Model metadata cache database table
The backend SHALL define a `ModelMetadataCache` SQLAlchemy model mapped to the `model_metadata_cache` table with columns: `id` (Integer primary key, autoincrement), `normalized_name` (String, unique, not null — the normalized base model name), `supports_reasoning` (Boolean, not null), `max_output_tokens` (Integer, nullable — null if unknown), `source_keys` (JSON, not null — array of original registry keys that mapped to this entry), `updated_at` (DateTime, not null). An Alembic migration SHALL create this table.

#### Scenario: Table created by migration
- **WHEN** the Alembic migration runs
- **THEN** the `model_metadata_cache` table exists with all specified columns and constraints

#### Scenario: Normalized name uniqueness enforced
- **WHEN** an entry with normalized_name "deepseek-r1" already exists and another insert with the same name is attempted
- **THEN** the database raises a unique constraint violation

### Requirement: Model name normalization
The backend SHALL implement a normalization function that transforms model names into a canonical form for registry lookup. The function SHALL: (1) take the last path segment after splitting on `/` (e.g. `deepseek/deepseek-r1` → `deepseek-r1`), (2) strip colon suffixes (e.g. `deepseek-r1:8b` → `deepseek-r1`), (3) strip `@` suffixes (e.g. `claude-3-7-sonnet@20250219` → `claude-3-7-sonnet`), (4) lowercase the result.

#### Scenario: Ollama-style model name
- **WHEN** normalizing `deepseek-r1:8b`
- **THEN** the result is `deepseek-r1`

#### Scenario: Provider-prefixed model name
- **WHEN** normalizing `deepseek/deepseek-r1`
- **THEN** the result is `deepseek-r1`

#### Scenario: Deep provider path
- **WHEN** normalizing `fireworks_ai/accounts/fireworks/models/deepseek-r1`
- **THEN** the result is `deepseek-r1`

#### Scenario: Vertex AI style with @ suffix
- **WHEN** normalizing `vertex_ai/claude-3-7-sonnet@20250219`
- **THEN** the result is `claude-3-7-sonnet`

#### Scenario: Plain model name
- **WHEN** normalizing `mistral`
- **THEN** the result is `mistral`

### Requirement: Registry fetch and index build
The backend SHALL implement a function to fetch the LiteLLM model registry from `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`, parse it, and build a normalized lookup index. For each entry in the registry (excluding the `sample_spec` key), the function SHALL normalize the key name, then aggregate entries by normalized name. For each normalized name: `supports_reasoning` SHALL be `true` if ANY entry with that normalized name has `supports_reasoning: true`; `max_output_tokens` SHALL be the minimum `max_output_tokens` value across all entries with that normalized name (conservative estimate), or null if no entries have the field. The function SHALL upsert rows into the `model_metadata_cache` table (insert or update on conflict by `normalized_name`). The function SHALL log a warning and return without error if the fetch fails (network error, non-200 status, invalid JSON).

#### Scenario: Successful registry fetch and index build
- **WHEN** the registry fetch function runs and the GitHub URL returns valid JSON
- **THEN** the `model_metadata_cache` table is populated with normalized entries, `updated_at` timestamps are set, and the function returns the count of entries upserted

#### Scenario: Registry fetch fails gracefully
- **WHEN** the registry fetch function runs and the GitHub URL is unreachable or returns non-200
- **THEN** the function logs a warning and returns without modifying the cache

#### Scenario: Registry JSON is invalid
- **WHEN** the registry fetch function runs and the response body is not valid JSON
- **THEN** the function logs a warning and returns without modifying the cache

#### Scenario: Reasoning flag aggregation across providers
- **WHEN** the registry contains `deepseek/deepseek-r1` with `supports_reasoning: true` and `fireworks_ai/.../deepseek-r1` with `supports_reasoning: false`
- **THEN** the normalized entry for `deepseek-r1` has `supports_reasoning: true` (any true wins)

#### Scenario: Max output tokens uses conservative minimum
- **WHEN** the registry contains entries for `deepseek-r1` with `max_output_tokens` values of 8192 and 128000
- **THEN** the normalized entry has `max_output_tokens: 8192` (minimum across providers)

### Requirement: Model metadata lookup
The backend SHALL implement a lookup function that takes a model name string and a database session, and returns metadata (`supports_reasoning`, `max_output_tokens`) or null values if no match. The lookup SHALL use two passes: (1) exact match on the normalized name in `model_metadata_cache`, (2) if no exact match, prefix match — find any cache entry whose `normalized_name` starts with `{normalized_input}-` or `{normalized_input}.`. If any prefix-matched entry has `supports_reasoning=true`, the result SHALL be `supports_reasoning=true`. The `max_output_tokens` SHALL be the minimum across all matched entries. If no match in either pass, return null for both fields.

#### Scenario: Exact match found
- **WHEN** looking up `deepseek-r1:8b` and `deepseek-r1` exists in the cache with `supports_reasoning=true`, `max_output_tokens=8192`
- **THEN** the lookup returns `{supports_reasoning: true, max_output_tokens: 8192}`

#### Scenario: Prefix match found
- **WHEN** looking up `qwen3:8b` and no `qwen3` exact entry exists, but `qwen3-30b-a3b` and `qwen3-coder-flash` exist with some having `supports_reasoning=true`
- **THEN** the lookup returns `{supports_reasoning: true, max_output_tokens: <min across matched entries>}`

#### Scenario: No match found
- **WHEN** looking up `totally-unknown-model:7b` and no entry matches
- **THEN** the lookup returns `{supports_reasoning: null, max_output_tokens: null}`

### Requirement: Weekly registry refresh
The backend SHALL refresh the model metadata cache on a weekly schedule. The refresh SHALL run as an async background task within the existing server process (same pattern as the task manager leader election). The refresh SHALL call the registry fetch and index build function. The refresh interval SHALL be 7 days from the last successful refresh. On server startup, if the cache table is empty or the most recent `updated_at` is older than 7 days, a refresh SHALL be triggered.

#### Scenario: Cache refreshed on startup when empty
- **WHEN** the server starts and the `model_metadata_cache` table is empty
- **THEN** the registry is fetched and the cache is populated

#### Scenario: Cache refreshed on startup when stale
- **WHEN** the server starts and the most recent `updated_at` in `model_metadata_cache` is older than 7 days
- **THEN** the registry is fetched and the cache is updated

#### Scenario: Cache not refreshed when fresh
- **WHEN** the server starts and the most recent `updated_at` is less than 7 days old
- **THEN** no registry fetch is performed

#### Scenario: Weekly background refresh
- **WHEN** 7 days have elapsed since the last successful refresh
- **THEN** the background task fetches the registry and updates the cache

### Requirement: On-demand registry refresh for unmatched models
When the model list endpoint serves a response containing models that have no match in the metadata cache (both exact and prefix match failed), the endpoint SHALL trigger an asynchronous background refresh of the registry cache. The refresh SHALL NOT block the response — the current request returns with null metadata for unmatched models, and the cache is updated for subsequent requests. The endpoint SHALL NOT trigger a refresh if the cache was refreshed within the last hour (debounce to avoid excessive fetches).

#### Scenario: Unmatched model triggers background refresh
- **WHEN** `GET /api/llm/providers/{id}/models` returns a model with no cache match and the last refresh was more than 1 hour ago
- **THEN** a background registry refresh is triggered and the response returns immediately with null metadata for the unmatched model

#### Scenario: Refresh debounced within 1 hour
- **WHEN** `GET /api/llm/providers/{id}/models` returns an unmatched model but the cache was refreshed less than 1 hour ago
- **THEN** no background refresh is triggered

#### Scenario: Subsequent request after refresh has metadata
- **WHEN** a background refresh completes and adds entries for previously unmatched models
- **THEN** the next call to `GET /api/llm/providers/{id}/models` returns metadata for those models
