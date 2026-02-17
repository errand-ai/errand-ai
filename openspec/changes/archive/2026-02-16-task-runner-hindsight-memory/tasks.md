## 1. Docker Compose: Hindsight Service

- [x] 1.1 Add `hindsight` service to `docker-compose.yml` using `ghcr.io/vectorize-io/hindsight:latest` image with ports 8888 (API) and 9999 (control plane UI), `HINDSIGHT_API_LLM_API_KEY=${OPENAI_API_KEY}`, `HINDSIGHT_API_LLM_BASE_URL=${OPENAI_BASE_URL:-}`, `HINDSIGHT_API_LLM_MODEL=claude-sonnet-4-5-20250929`, persistent volumes for pg0 data and model cache, an init container for volume permissions, and a healthcheck
- [x] 1.2 Add `HINDSIGHT_URL=http://hindsight:8888` environment variable to the worker service in `docker-compose.yml`

## 2. Worker: Hindsight MCP Injection

- [x] 2.1 Add Hindsight URL and bank ID resolution in `process_task_in_container`: read `HINDSIGHT_URL` env var falling back to `hindsight_url` setting, read `HINDSIGHT_BANK_ID` env var falling back to `hindsight_bank_id` setting (default `content-manager-tasks`)
- [x] 2.2 Inject `hindsight` MCP server entry into `mcpServers` dict with URL `{hindsight_url}/mcp/{bank_id}/` (skip if already present in database config), following the existing Perplexity/backend injection pattern
- [x] 2.3 Append Hindsight memory usage instruction section to system prompt when Hindsight is configured, instructing the agent to use `retain`, `recall`, and `reflect` tools

## 3. Worker: Memory Pre-loading

- [x] 3.1 Add `recall_from_hindsight(hindsight_url, bank_id, query, max_tokens=2048)` function that calls `POST {hindsight_url}/v1/default/banks/{bank_id}/memories/recall` via `httpx` and returns the recalled text (or `None` on failure)
- [x] 3.2 Call `recall_from_hindsight` in `process_task_in_container` before writing system prompt, using task title + description as the query
- [x] 3.3 Inject recalled content into system prompt as `## Relevant Context from Memory` section (after admin system prompt, before Perplexity/skill/MCP instructions)

## 4. Worker Tests

- [x] 4.1 Add test for `recall_from_hindsight` with successful recall response
- [x] 4.2 Add test for `recall_from_hindsight` with API failure (returns `None`, logs warning)
- [x] 4.3 Add test for Hindsight MCP injection into `mcpServers` dict
- [x] 4.4 Add test for Hindsight MCP injection skipped when already in database config
- [x] 4.5 Add test for memory context section injected into system prompt
- [x] 4.6 Add test for Hindsight skipped entirely when URL not configured
- [x] 4.7 Verify existing worker tests still pass with Hindsight integration

## 5. Helm Chart

- [x] 5.1 Add `hindsight.url` and `hindsight.bankId` values to `helm/content-manager/values.yaml` (default empty URL, default bank ID `content-manager-tasks`)
- [x] 5.2 Add `HINDSIGHT_URL` and `HINDSIGHT_BANK_ID` environment variables to worker deployment template, sourced from the new values

## 6. Version Bump

- [x] 6.1 Bump `VERSION` file for this feature addition
