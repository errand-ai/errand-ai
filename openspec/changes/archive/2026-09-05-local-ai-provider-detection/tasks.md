## 1. Branch and version

- [x] 1.1 Create branch `local-ai-provider-detection` from an up-to-date `main`, after `bundle-hindsight-runtime` has merged
- [x] 1.2 Bump `VERSION` (minor — new API surface, new provider source, changed compose networking)

## 2. Settle the open questions before building on them

- [x] 2.1 Measure a cold local runtime: time from first request to first token with no model loaded. Record whether the existing 30 s default request timeout survives it
- [x] 2.2 Decide the timeout treatment — a higher default for detected providers, or separating first-token wait from total request timeout — and replace the open question in `design.md` with the decision
- [x] 2.3 Decide the API-key sentinel for keyless local runtimes and record it in `design.md`

## 3. Host reachability

Independently useful; a locally detected provider is unusable without it.

- [x] 3.1 Write failing tests: task containers receive a host entry when a gateway address is configured, and are created unchanged when it is not
- [x] 3.2 Read `HOST_GATEWAY_ADDRESS` with a `host.docker.internal` default, treating an empty value and the Kubernetes runtime as "detection unavailable"
- [x] 3.3 Add the host entry to task containers in the Docker runtime
- [x] 3.4 Add the host gateway mapping to the errand and memory services in both compose files
- [x] 3.5 Verify from inside a running task container that a host-run OpenAI-compatible service is reachable by the gateway name

## 4. Refuse host networking for detected providers

- [x] 4.1 Write a failing test: a task resolving a detected provider fails with an explicit error when task containers would use host networking
- [x] 4.2 Implement the guard, naming the required configuration in the error
- [x] 4.3 Confirm tasks using non-detected providers under host networking are unaffected

## 5. Local AI detection

- [x] 5.1 Write failing tests: a responding endpoint is registered with the gateway-based URL; re-scan upserts rather than duplicates; a departed runtime is reconciled away; manually configured providers are untouched; an empty scan reports nothing found rather than failing
- [x] 5.2 Add the fixed candidate table, keyed by runtime name and default port
- [x] 5.3 Implement the scan, reusing the existing provider type probe and following the environment-provider reconciliation pattern with `source="detected"`
- [x] 5.4 Identify services from the probe response rather than the port, and cover the shared-8080 case in a test
- [x] 5.5 Set the default provider only when no provider exists at all
- [x] 5.6 Expose the scan as an API operation, reporting unavailability rather than failure where there is no reachable host
- [x] 5.7 Write failing tests: a detected provider with no configured timeout yields the longer default; an explicit profile timeout wins; an explicit global setting wins; a non-detected provider is unchanged
- [x] 5.8 Apply the longer default in the task manager's timeout resolution (D9)

## 6. Provider catalog

- [x] 6.1 Re-verify every catalogued base URL before shipping — an unauthenticated request to the listing endpoint returning 401 or 403 confirms the endpoint exists; 404 or a DNS failure means the entry is wrong
- [x] 6.2 Add the catalog with display name, base URL, model-listing support and key-acquisition reference per entry
- [x] 6.3 Mark entries that do not support model listing, including the Gemini OpenAI-compatible surface
- [x] 6.4 Add the unlisted OpenAI-compatible entry taking a caller-supplied base URL
- [x] 6.5 Expose the catalog through the API and create providers from a selected entry, probing exactly as for manual entry

## 7. Model mode

- [x] 7.1 Write failing tests: a chat model and an embedding model are classified from the registry; a local-runtime name is reconciled by the alternate normalisation; an unknown model reports unknown without error
- [x] 7.2 Extract `mode` in the metadata registry alongside the existing capability fields
- [x] 7.3 Prefer a provider-reported mode over the registry lookup
- [x] 7.4 Make mode filtering work for providers that do not report mode natively, keeping unknown-mode models selectable

## 8. Provider reachability

- [x] 8.1 Write a failing test: a reachability check reports unreachable without mutating stored configuration
- [x] 8.2 Implement the check and expose it through the API

## 9. Settings UI

Requires a `@errand-ai/ui-components` release and a consumer bump. Everything else ships without it.

**Delegated, and now landed.** `TaskManagementPage.vue` renders `<LlmProviderCard />` from `@errand-ai/ui-components` and owns no provider UI of its own, so none of 9.1–9.5 could be implemented in this repository. They became `provider-catalog-and-local-ai-ui` in `errand-component-library` — the same route `context-usage-visibility` took for the turn badge. That shipped in v0.19.0 (alongside `surface-readonly-settings`, under one tag), and the pin is bumped in this branch from `^0.18.0` to `^0.19.0`; the lockfile diff touches only that entry.

Verified against the published component rather than trusting the pin. `frontend/src/components/__tests__/LlmProviderCardSeam.test.ts` mounts the real card and drives it with responses captured verbatim from this repo's own endpoints (`fixtures/provider-api-capture.json`, produced by running the FastAPI app under its test client). That guards the seam neither repo's suite can see: the library tests its rendering against fixtures it wrote, errand tests its responses against fixtures it wrote, and whether the fields one emits are the fields the other reads is checked only there — across five response shapes, not one. 23 assertions, all passing.

- [x] 9.1 Write failing frontend tests: choosing a listed provider asks only for a key; the unlisted entry reveals base URL and key; a provider without listing accepts a typed model; a large model list is filterable
      — *implemented in `errand-component-library` → `provider-catalog-and-local-ai-ui`, groups 3–7. Covered from this side by the seam test.*
- [x] 9.2 Replace free-text provider creation with catalog selection plus the unlisted entry
      — *implemented there, group 3. The seam test asserts the create call sends `catalog_id` and no invented base URL, and that an older server with no catalog endpoint falls back to typed entry rather than an empty dropdown.*
- [x] 9.3 Add the scan control, with a distinct message for "nothing found" and for "detection unavailable"
      — *implemented there, group 4. Both messages verified distinct against the real component: an empty scan says "no local AI" without an alert role, and `{available: false}` says "not available" — telling a Kubernetes user to go start Ollama would send them somewhere that can never work.*
- [x] 9.4 Show reachability per provider with a re-check action
      — *implemented there, group 5. The seam test pins the part most easily lost: a provider whose check has not returned shows unknown, never reachable, and the list renders without waiting.*
- [x] 9.5 Label detected providers as detected
      — *implemented there, group 6, which also removed Edit and Delete from env-sourced rows. One finding from the seam test: the card keeps Edit on a detected provider and locks the base URL inside the form, explaining it is refreshed by the next scan — my first assertion expected Edit to be absent and was wrong about the requirement, not about the card.*

## 10. Reposition LiteLLM

- [x] 10.1 Update documentation to recommend an aggregator or a local runtime as the starting point, and present a self-hosted proxy as an advanced option
- [x] 10.2 Confirm existing LiteLLM deployments are unaffected: provider type, the MCP gateway capability and the MCP settings card all behave as before
- [x] 10.3 Update `CLAUDE.md` where it describes the provider model

## 11. Verify

Run against the local stack after v0.19.0 landed, so one pass covered both the backend and the released card.

- [x] 11.1 Run the full errand and frontend test suites
      — *2218 errand, 275 frontend, 165 task-runner, 38 evals. CLAUDE.md's task-runner count was stale at 412 and is corrected; that directory is untouched by this change.*
- [x] 11.2 End to end with a local runtime on the host: scan, adopt, select, run a task, confirm the task container reached the host service
      — *Ollama on the host, errand and the task-runner in containers on `errand-net`. The scan found it and stored `http://host.docker.internal:11434/v1` — the gateway address, not localhost. The env-sourced LiteLLM provider stayed default, so D6 held on a non-empty install. The chat filter returned only `gpt-oss:20b`, correctly excluding the two `qwen3-embedding` models by registry mode — D8 working on real local model names, which a substring heuristic would have got wrong. The task completed with output `OK`, and the runner log carries the line this whole change exists for: `POST http://host.docker.internal:11434/v1/chat/completions "HTTP/1.1 200 OK"`, issued from inside the task container. D9 confirmed in the same run: `LLM request timeout set to 300.0s`.*
- [x] 11.3 End to end with a catalogued hosted provider: create from the catalog, list models, run a task
      — *Created from the catalog with the name omitted, and it defaulted to the entry's display name; the type was probed to `openai_compatible` exactly as for manual entry. Model listing returned 53 models with mode resolved per model — `claude-haiku-4-5-20251001` as chat, the MLX entries as unknown and kept rather than dropped. An unknown `catalog_id` and the unlisted entry with no base URL were both refused with 422.*
      — *The task run against that provider failed on a 503 from the remote LiteLLM proxy's upstream routing — the proxy itself was up (`/v1/models` 200), so this was an external outage, not this change. The run was repeated through the catalog's unlisted OpenAI-compatible entry pointed at the local runtime, which isolates the catalog path from that dependency: created, listed, task completed with `OK`. That provider is `source="database"` and took the standard `30.0s` timeout, which is the other half of D9.*

## 12. Archive

- [x] 12.1 `openspec archive local-ai-provider-detection -y` and commit the result in this PR
      — *18 requirements added and 1 modified across five capabilities. The modified one is `Per-provider model listing`: the previous text said OpenAI-compatible providers got no mode filtering, which this change contradicts.*

## Post-merge notes

- `converge-provider-config` in errand-desktop depends on the scan operation and catalog landing here; it can start once this is merged.
- Catalogued base URLs need periodic re-verification; the unlisted entry means a stale catalog degrades rather than blocks.
