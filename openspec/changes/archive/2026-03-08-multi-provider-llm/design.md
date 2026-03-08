## Context

Errand currently assumes a single LLM provider configured via `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables (or equivalent DB settings). A single `AsyncOpenAI` client is initialized at startup and shared across all LLM operations. Model selection (title generation, task processing, transcription) is a flat string stored in the settings table.

This worked when all users ran LiteLLM as a proxy, but users who want to use multiple providers directly — or route different model roles through different endpoints — cannot do so.

## Goals / Non-Goals

**Goals:**
- Support N LLM providers, each with independent base URL, API key, and detected type
- Allow model settings to reference a specific provider
- Maintain the env-var-overrides-DB pattern (env-sourced providers are readonly in UI)
- Auto-detect provider type (LiteLLM vs OpenAI-compatible vs unknown) on registration
- Encrypt stored API keys using existing Fernet infrastructure
- Clean migration path for Helm chart values

**Non-Goals:**
- Backward compatibility with `OPENAI_BASE_URL`/`OPENAI_API_KEY` env vars (clean break)
- Provider-specific model listing beyond LiteLLM's `/model/info` and OpenAI-compatible `models.list()` (future work)
- Load balancing or failover across providers
- Per-user provider configuration (providers are system-wide, admin-managed)

## Decisions

### 1. New `llm_provider` table instead of JSON in settings

**Decision**: Create a dedicated `llm_provider` SQLAlchemy model and database table.

**Rationale**: Providers are a first-class entity with encrypted credentials, referential relationships to model settings, and a lifecycle (create/probe/update/delete). Storing them as JSON inside the settings table would complicate encryption, validation, and cascade logic. The existing `CREDENTIAL_ENCRYPTION_KEY` / Fernet setup (used by cloud storage OAuth) provides the encryption infrastructure.

**Alternatives considered**:
- JSON blob in settings table: simpler schema but no per-field encryption, harder to reference from model settings, messy cascade logic
- Separate config file: doesn't work for DB-managed providers, breaks the settings UI pattern

### 2. Indexed env vars (`LLM_PROVIDER_{N}_*`)

**Decision**: Use numbered env vars scanned at startup: `LLM_PROVIDER_{N}_NAME`, `LLM_PROVIDER_{N}_BASE_URL`, `LLM_PROVIDER_{N}_API_KEY`. Index 0 is the default provider.

**Rationale**: Indexed vars map cleanly to Helm template `range` loops over a `llmProviders[]` values array. They're explicit, debuggable, and don't require JSON parsing. The `DEFAULT=true` flag was rejected — index 0 is always default, reducing config surface.

**Alternatives considered**:
- Name-keyed vars (`LLM_PROVIDER_LITELLM_BASE_URL`): names with special chars are problematic in env var names
- JSON blob var: harder to debug, doesn't map to Helm secret refs
- Keep legacy `OPENAI_*` as default: adds backward-compat complexity we don't need

### 3. Provider type probing on creation

**Decision**: When a provider is created (or its URL changes), probe the base URL to detect its type:
1. `GET {base_url}/../model/info` (stripping `/v1` suffix) — if it responds with LiteLLM's format → `litellm`
2. `GET {base_url}/models` with the API key — if it responds → `openai_compatible`
3. Neither responds → `unknown`

Store the result as `provider_type` enum on the provider row.

**Rationale**: This determines model listing behavior — LiteLLM gets filtered transcription lists, OpenAI-compatible gets full model lists, unknown gets free-text input. Probing on creation avoids per-request latency.

**Alternatives considered**:
- User-selected type dropdown: extra UX friction, users may not know
- Probe on every model list: slower, unnecessary when type rarely changes

### 4. Model settings as `{provider_id, model}` pairs

**Decision**: Change `llm_model`, `task_processing_model`, and `transcription_model` settings from flat strings to JSON objects: `{"provider_id": "<uuid>", "model": "<model-id>"}`.

**Rationale**: A model name alone is ambiguous across providers (e.g., "gpt-4o" might exist on both a LiteLLM proxy and direct OpenAI). The provider_id creates an unambiguous reference.

### 5. Client pool with lazy creation and invalidation

**Decision**: Replace the single global `AsyncOpenAI` client with a dict cache keyed by provider UUID. Clients are created lazily on first use and evicted when a provider is updated or deleted.

**Rationale**: Creating all clients at startup wastes connections for rarely-used providers. Lazy creation + invalidation on mutation keeps things simple.

### 6. Provider deletion cascades to model settings

**Decision**: When a provider is deleted, any model settings referencing it are cleared (set to null/empty). The frontend detects unconfigured models and prompts the user to select replacements. The default provider (index 0 / env-sourced) cannot be deleted via the UI.

**Rationale**: Blocking deletion until models are reassigned would require a multi-step UI flow. Clearing and prompting is simpler and makes the consequence visible immediately.

**Alternatives considered**:
- Block deletion: requires reassignment UI before delete, more complex
- Fall back to default provider: might silently use wrong model

### 7. Helm `llmProviders[]` array with per-provider secret support

**Decision**: Replace `openai.baseUrl`/`openai.apiKey`/`openai.existingSecret` with:
```yaml
llmProviders:
  - name: litellm
    baseUrl: "https://litellm.example.com/v1"
    apiKey: ""
    existingSecret: ""
    secretKeyApiKey: ""
```

The deployment template iterates with `range` and renders indexed env vars. If `existingSecret` is set for a provider, the API key comes from that secret; otherwise from `apiKey` value directly.

### 8. Per-provider model listing endpoint

**Decision**: `GET /api/llm/providers/{id}/models` replaces both `/api/llm/models` and `/api/llm/transcription-models`. The endpoint returns all models for the provider. For LiteLLM providers, an optional `?mode=audio_transcription` query param filters via `/model/info`.

**Rationale**: One endpoint per provider is cleaner than a global endpoint that needs to know which provider to query. The mode filter preserves LiteLLM's transcription filtering without a separate endpoint.

## Risks / Trade-offs

- **Env var scanning order matters** — If env var indices have gaps (0, 2 but no 1), the scanner must handle this gracefully. Mitigation: scan sequentially, stop at first missing index.
- **Provider probe is best-effort** — A provider behind a firewall or slow network might be misclassified as `unknown`. Mitigation: allow manual type override in the edit UI (future enhancement).
- **Client pool memory** — Each provider gets its own `AsyncOpenAI` instance with connection pool. Mitigation: in practice users will have 2-5 providers, not hundreds.
- **Breaking change** — Existing deployments must update env vars and Helm values. Mitigation: document the migration clearly in release notes; the change is straightforward (rename vars, restructure values).

## Open Questions

- None — all major decisions resolved during exploration.
