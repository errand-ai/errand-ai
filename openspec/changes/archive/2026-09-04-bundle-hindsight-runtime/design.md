## Context

Hindsight is a separate service in every deployment errand supports. This change does not alter that. It changes which image is started, how it is configured, and who supplies its secrets.

The measurements below were taken on this machine (arm64, Docker 28.4.0, 4 vCPU / 7.7 GiB) against `hindsight-api:latest-slim` and `hindsight-api:latest`, and are reproduced here because several contradict the upstream documentation.

## Decisions

### D1 — Derive from `slim`, do not fork and do not use `full`

`slim` already contains everything the ONNX path needs except one package:

```
onnxruntime      1.20.1   present (32 MB)
tokenizers       0.22.2   present
huggingface_hub  1.6.0    present
OnnxEmbeddings            present (engine/embeddings.py)
FlashRankCrossEncoder     present (engine/cross_encoder.py)
transformers              ABSENT  ← blocks OnnxEmbeddings.initialize()
```

`OnnxEmbeddings.initialize()` does `from transformers import AutoTokenizer` and raises `ImportError` without it. Adding `transformers` (54 MB) and `flashrank` (24 KB installed) pulls **no torch** — verified in-container, and now asserted at build time.

The derived image is two lines. It is not a fork, and nothing is patched:

```dockerfile
FROM ghcr.io/vectorize-io/hindsight-api:<pinned>-slim
RUN VIRTUAL_ENV=/app/api/.venv uv pip install --no-cache transformers flashrank
```

Note `uv`, not `pip`: the image's venv at `/app/api/.venv` has no `pip` binary. `uv` is on `PATH` at `/usr/local/bin/uv`.

**Correction: "exactly two packages" is not literally what the install does.** Measured against `0.9.2-slim`, `uv pip install transformers==5.16.1 flashrank==0.2.10` resolves to four changes, not two:

```
+ FlashRank    0.2.10
+ transformers 5.16.1
+ safetensors  0.8.0     (transformers dependency; compiled, not pure Python)
~ tokenizers   0.22.2 -> 0.23.2   (upgraded, i.e. a base package is replaced)
```

Constraining to `transformers<5` to avoid touching `tokenizers` was measured and is **worse**: it resolves to `transformers 4.57.6` and *downgrades* `huggingface-hub` from the base's 1.6.0 to 0.36.2. The base itself uses `huggingface_hub`, so a forward-compatible bump of a tokenizer is preferable to a downgrade of a library the base depends on. Both added packages are therefore pinned to exact versions, for the same reason the base tag is pinned.

The load-bearing half of the claim is unaffected and is enforced rather than asserted: the build fails if `torch` or `sentence_transformers` is importable.

### D1a — The pinned base tag is `0.9.2-slim`

`0.9.2-slim` is the newest published slim tag at the time of writing (162 tags enumerated from the GHCR tag list for `vectorize-io/hindsight-api`; the highest non-signature tags are `0.9.2` and `0.9.2-slim`). Its manifest digest is
`sha256:7635a15739361dbdf221ba796ad25a813f876144fe113022eea8e26cb6ee75e7` — **byte-identical to `latest-slim`**, so pinning it costs nothing in currency and buys the whole point of the pin: an upstream release cannot silently change what errand publishes.

It is named as a version tag rather than as a digest so that Renovate can recognise and bump it (D-CI below), and so the Dockerfile stays readable. The build-time assertion is what actually guards against a bad base, not the tag form.

### D2 — Bake the models

Cold start with an empty cache was **135 s** (HF download of the ONNX graph, then FlashRank fetching `ms-marco-MiniLM-L-12-v2`); warm start was **40 s**. Baking both into the image removes the network dependency from first run entirely, which matters more for the target audience than the size it adds.

**Correction: it adds ~530 MB, not ~120 MB, and the finished image is 3.85 GB, not 2.98 GB.** Measured on the built image:

| layer | size |
|---|---|
| `transformers` + `flashrank` + `safetensors` + the `tokenizers` bump | 70 MB |
| `intfloat/multilingual-e5-small` graph + tokenizer | 494 MB |
| FlashRank `ms-marco-MiniLM-L-12-v2` | 37 MB |
| bytecode cache written by the build-time self-test | 18 MB |

The estimate was out because `multilingual-e5-small`'s `onnx/model.onnx` is a **470 MB fp32 export** — the model is small in parameters but multilingual, so the token-embedding matrix dominates. A quantised variant would cut this sharply, but the quality numbers in D3 were measured against the default `onnx/model.onnx`, and re-deciding the model on size grounds would invalidate them. Not done here.

| image | measured (`docker images`, arm64) |
|---|---|
| upstream `0.9.2-slim` | 2.90 GB |
| **`errand-hindsight`** | **3.85 GB** |
| upstream full (`hindsight-api:latest`) | 5.47 GB |

The conclusion survives the correction — 1.6 GB smaller than full, and no torch — but the headline "2.98 GB" from the proposal is wrong and should be read as 3.85 GB.

Two things were needed to keep it at 3.85 GB rather than 4.75 GB, both counter-intuitive enough to be worth recording:

- **Do not `chown -R` the model directory after populating it.** Chown rewrites every file, so the layer is an exact duplicate of the models: +549 MB measured. Create the directory owned by the runtime user while it is still empty and download as that user instead.
- **Do not fetch the model with `*.json` / `*.model` globs.** The repo carries a second copy of the tokenizer inside `onnx/` (`tokenizer.json` alone is 17 MB) plus sentence-transformers metadata this image never loads. Enumerate the wanted files explicitly, and delete the `.cache` directory `snapshot_download` leaves inside `local_dir` in the same layer.

### D3 — `flashrank` is mandatory; `rrf` is a fallback, not a default

This reverses an earlier working assumption. Measured on one bank, changing only the reranker:

```
onnx + flashrank   recall@1 0.87   recall@5 0.93   MRR 0.887
onnx + rrf         recall@1 0.40   recall@5 0.60   MRR 0.547
```

`rrf` is rank-fusion passthrough with neural reranking disabled. It belongs only as the last member of a reranker chain, where it makes recall fail open rather than error.

### D4 — One database, two schemas

`HINDSIGHT_API_DATABASE_SCHEMA` (default `public`) lets Hindsight own a `hindsight` schema inside errand's existing database. Alembic keeps `public`. This removes `CREATE DATABASE hindsight` from the compose init script and removes the second-database problem from any future Kubernetes work.

Accepted trade-off: `pg_dump` of the errand database now contains memory, and there is no way to reset errand's tasks without also dropping memory. For compose that is already true of `docker compose down -v`. The schema boundary is treated as a real boundary — Hindsight owns `hindsight`, alembic never touches it, and no errand code assumes it exists.

### D4a — `pg_trgm` must be pre-created in `public`, or memory silently never appears

The single worst failure found while verifying this change, and the one nothing in the plan anticipated.

Moving Hindsight into a schema of errand's database makes PostgreSQL extension placement load-bearing: an extension is registered per *database* but its objects live in exactly one *schema*, and operator resolution goes through `search_path`.

Left to itself, Hindsight in schema mode creates `pg_trgm` **in its own tenant schema**, where its runtime cannot resolve the `%` operator. The consequence, reproduced on a fresh volume:

```
asyncpg.exceptions.UndefinedFunctionError: operator does not exist: text % text
  ... engine/entity_resolver.py, in _resolve_entities_batch_trigram
Task ... scheduled for retry at ... (one-minute backoff, indefinitely)
```

**The failure is silent from every angle that matters.** The container is healthy. The MCP `retain` call returns `{"status":"accepted"}` and the agent reports success. Only the asynchronous batch retain fails, over and over, so the sole symptom is that memory never appears — no error reaches the task, the log, or the user.

The fix is one line in the database init script:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

It works because `CREATE EXTENSION IF NOT EXISTS` matches on the *database*, not the schema: creating it in `public` first makes Hindsight's own mis-placed create a no-op. That is also why getting the schema wrong here is worse than omitting the line — a wrong placement cannot be recovered without an `ALTER EXTENSION ... SET SCHEMA`.

`vector` goes in `public` for a related but different reason: Hindsight enforces that placement itself, logging `pgvector extension found in schema 'hindsight' instead of 'public'. Attempting to relocate...` and moving it on every fresh start if it is anywhere else.

Measured resolution, with the operator in `public`:

| `search_path` | `'abc' % 'abd'` |
|---|---|
| `hindsight` | fails |
| `public` | resolves |
| `hindsight, public` | resolves |

`errand/tests/test_compose_hindsight.py` pins both extensions and asserts neither carries an explicit `SCHEMA` clause, because the failure mode is a silent no-op rather than an error.

Reported upstream as [vectorize-io/hindsight#4118](https://github.com/vectorize-io/hindsight/issues/4118): schema mode creates an extension its own runtime cannot use, and the failure reaches nobody. Until it is fixed, the init-script line above is what makes schema mode usable at all.

### D5 — errand generates the bearer that authenticates Hindsight

Hindsight's MCP endpoint is open by default. errand already resolves `hindsight_token` env-var-first, and already mints `mcp_api_key` and the workspace bearer. When no token is configured from either source, errand generates one, persists it as the `hindsight_token` setting, and the deployment passes the same value to the Hindsight container. Precedence is unchanged: an explicitly configured token still wins, so nothing existing changes behaviour.

**Correction made during implementation.** This decision was written against `HINDSIGHT_API_MCP_AUTH_TOKEN`. **That environment variable does not exist.** Read at upstream `main`, `hindsight-api-slim/hindsight_api/config.py` defines only four MCP variables — `HINDSIGHT_API_MCP_ENABLED`, `..._ENABLED_TOOLS`, `..._STATELESS`, `..._INSTRUCTIONS` — and none of them concerns authentication. There is no bearer check anywhere in `main.py` or `server.py`.

Authentication is instead a *tenant extension*, documented in `hindsight-docs/versioned_docs/version-0.9/developer/mcp-server.md` ("By default, the MCP endpoint is **open** (no authentication required)") and implemented by `hindsight_api/extensions/builtin/tenant.py`:

```
HINDSIGHT_API_TENANT_EXTENSION=hindsight_api.extensions.builtin.tenant:ApiKeyTenantExtension
HINDSIGHT_API_TENANT_API_KEY=<the bearer>
```

`ApiKeyTenantExtension.authenticate()` compares `context.api_key` against `HINDSIGHT_API_TENANT_API_KEY` and raises `AuthenticationError` on a mismatch; `authenticate_mcp()` delegates to it. Missing or wrong key ⇒ `401`. The behaviour D5 asks for is reached exactly; only the variable name was wrong.

### D5a — Turning on the tenant extension authenticates the whole API, not only `/mcp`

`ApiKeyTenantExtension` sits in the tenant-resolution path, which every request traverses — `authenticate()` for REST, `authenticate_mcp()` for MCP. Enabling it therefore closes the entire Hindsight HTTP surface, which is broader than the requirement's wording ("the MCP endpoint is authenticated rather than open by default"). Three consequences, all of which this change already has to handle:

- **The Control Plane becomes a client that must authenticate.** It reads `HINDSIGHT_CP_DATAPLANE_API_KEY` (`hindsight-control-plane/src/lib/hindsight-client.ts`) and sends it as `Authorization: Bearer`. Task 6.3 already calls for wiring the Control Plane's bearer from the same value as the API's, so this costs nothing extra — but it is now load-bearing rather than optional: without it, the opt-in Control Plane profile starts and then 401s on every call.
- **`memory-status-panel` inherits the requirement.** errand makes no REST calls to Hindsight today (it only injects the MCP URL and header into the task runner's `mcp.json`), so nothing breaks now. Any future server-side REST call must carry the same bearer.
- **The default schema still applies.** Both `DefaultTenantExtension` and `ApiKeyTenantExtension` return `TenantContext(schema_name=get_config().database_schema)`, so enabling the extension does not disturb D4 — `HINDSIGHT_API_DATABASE_SCHEMA=hindsight` continues to select the schema.

Closing the whole surface is the right default here regardless: an unauthenticated Hindsight on a shared network exposes read *and write* access to every memory, and the REST API is the more capable of the two surfaces.

Not used: `HINDSIGHT_API_TENANT_MCP_AUTH_DISABLED`, which re-opens `/mcp` for backwards compatibility. It exists, and it would defeat the point.

### D7 — `testing/`'s Hindsight LLM model is overridable, and its default now answers

Not in the original plan; found while verifying task 9.3. `testing/docker-compose.yml` hard-coded `HINDSIGHT_API_LLM_MODEL: claude-sonnet-4-5-20250929`, which on this proxy fails with `BedrockException Invalid Authentication`. Because Hindsight only reaches for the LLM during fact extraction, the failure never appears at start-up or in a healthcheck — it surfaces as a `sync_retain` error, several layers down, long after everything looks fine.

Changed to `${HINDSIGHT_API_LLM_MODEL:-minimax-m2.5:free}`, which matches `deploy/`'s existing overridable form and picks a default that carries a fallback chain, so an unavailable model degrades to another rather than erroring. This is a fix to a broken default in a file this change already edits, not a widening of scope.

### D6 — Control Plane behind a profile, default off

compose gets `profiles: ["memory-ui"]`, so `docker compose up` no longer starts it and `9999:9999` is no longer published. `workspace-gateway` already uses this mechanism, so it is house style. It is framed as a debug/advanced tool, not a feature — which is defensible only because `memory-status-panel` covers the everyday questions.

## Measurements that contradict upstream documentation

Recorded so nobody re-derives them:

| Claim in Hindsight docs | Measured here |
|---|---|
| slim ≈ 500 MB | **2.90 GB** on disk (arm64); 500 MB is the compressed registry figure |
| full ≈ 3.7 GB arm64 | **5.47 GB** (`hindsight-api`), 5.83 GB (standalone `hindsight`) |
| full needs 1.5–2 GB RAM, slim 0.5–1 GB | Under identical load: full **892 MiB**, slim+onnx **1.35 GiB** — slim+onnx uses *more* |

The RAM inversion is most likely ONNX Runtime's CPU memory arena. `HINDSIGHT_API_RERANKER_FLASHRANK_CPU_MEM_ARENA` defaults to `false` and was `false` in the measurement, so 1.35 GiB is a floor rather than a ceiling. **The derived image's win is disk and download size, not memory.**

## Risks

- **Base-image drift.** A `slim` release could move the venv path, drop the ONNX provider, or vendor `transformers` itself. Mitigated by pinning an exact base tag and by a build-time assertion (task 3.4) that fails the build rather than shipping an image whose ONNX path is broken.
- **Corpus-shape validity.** The quality comparison used `chunks` mode, which indexes whole chunks. Real memories are LLM-extracted atomic facts — shorter and differently phrased. `e5-small` and BGE are equivalent on chunks; that is not proof they are equivalent on facts.
- **Sample size.** n=15 queries; one query is 6.7 points. The correct reading is "no detectable difference between the derived image and full", not "the derived image is better".

## Open Questions

- **Upstream issue (task 2.1/2.2): filed as [vectorize-io/hindsight#4116](https://github.com/vectorize-io/hindsight/issues/4116).** Reports that the slim image ships `onnxruntime`, `tokenizers`, `huggingface_hub` and the `OnnxEmbeddings` provider but not `transformers`, so `OnnxEmbeddings.initialize()` cannot run. If it is accepted, the derived image in this change reduces to stock slim plus `flashrank` and the baked models — or disappears entirely. The draft is kept at `upstream-issue.md` in this change directory.
- **Second upstream issue: filed as [vectorize-io/hindsight#4118](https://github.com/vectorize-io/hindsight/issues/4118).** In schema mode Hindsight creates `pg_trgm` in its tenant schema, where its own runtime cannot resolve `%`, and every retain then fails silently (see D4a). Unlike the first, this is a defect rather than a packaging gap; errand works around it in the database init script, and that workaround should stay until the fix ships, since removing it re-breaks memory silently.
- Should the upstream gap be reported? `slim` ships 32 MB of onnxruntime plus the provider and cannot use it for want of one pure-Python package. If upstream adds `transformers` to `slim`, this entire image disappears and errand runs stock. Filing costs one issue and is worth doing in parallel with implementing.
- Does `e5-small` hold up against BGE on LLM-extracted facts rather than chunks? Answering needs a working extraction path; see the note below.

## What the compose bring-up actually verified

A `docker compose -f testing/docker-compose.yml --profile memory-ui up -d` against **empty volumes**, with the corrected init script, produced:

- **One database, two schemas.** `content_manager` only; `public` holds errand's 20 tables, `hindsight` holds Hindsight's 23. Each has its own `alembic_version` — errand's in `public`, Hindsight's in `hindsight`. Both extensions land in `public`, with no relocation warning.
- **The image defaults are live and need no compose configuration.** The container logs `Embeddings: provider=onnx` / `Reranker: provider=flashrank` and loads from `/opt/hindsight-models/multilingual-e5-small/onnx/model.onnx` at `dim: 384`, with no embeddings or reranker environment variables set anywhere in the compose file.
- **Authentication works in both directions.** `POST /mcp/errand-tasks/` returns `401` unauthenticated, and completes the MCP handshake and `tools/list` (returning `retain`, `recall`, `reflect`, …) with the compose bearer. `/health` stays open, so the healthcheck is unaffected — which is why the tenant extension can be enabled by default.
- **The Control Plane is opt-in and closed.** Absent from a default bring-up; started under `--profile memory-ui` it serves, and `GET /api/banks` without its session cookie is `401`.
- **The settings API masks the token.** `hindsight_token` reads back `erra****` (source `env`, sensitive, readonly) and the literal value appears nowhere in the payload, while `mcp_api_key` is still returned in full — masking is per-key, not a blanket change.
- **Generation works against real PostgreSQL, not just the SQLite unit tests.** With `HINDSIGHT_TOKEN` unset, `ensure_hindsight_token` generated a 64-character token, persisted it, returned the same value on a second call in a fresh session, and the settings API reported it masked with source `database`. With the variable set, no row is written at all — an env-sourced token must not be copied into the database, or unsetting it would silently leave the old value in force.
- **A task retained, end to end.** An errand task called the `retain` tool through the authenticated MCP endpoint; Hindsight extracted facts via the LLM and wrote **memory units with 384-dimension embeddings**, plus entities and a document, into the `hindsight` schema. Zero `text % text` errors on the clean run. That is the baked ONNX model, reached from a real task, through the schema-isolated database, with the generated bearer.
- **And recalled it.** A second task called `recall` with a paraphrased query — "where does errand-hindsight keep its ONNX embedding model" — and got the stored fact back: *"The errand-hindsight container image includes the multilingual-e5-small ONNX embedding model baked into /opt/hindsight-models, enabling first run without network access."* Retrieval ran through the local ONNX embedding of the query and the FlashRank reranker, both from the baked artefacts. The round trip is closed.

Two things had to be corrected before that last item passed, both recorded above: `HINDSIGHT_API_LLM_MODEL` in `testing/` pointed at a model this proxy rejects (D7), and `pg_trgm` was being created where Hindsight could not resolve `%` (D4a). Neither was visible without running the stack.

## Note on the environment used for measurement## Note on the environment used for measurement

The original test design used real LLM extraction and had to be abandoned: on `litellm.devops-consultants.net` every Claude model returns `BedrockException Invalid Authentication`, every Ollama-backed model returns `503 No server is available`, and `gpt-oss:20b` took **166 s** for one 2,811-token extraction, tripping Hindsight's own `[STUCK_STACK] age=625s threshold=600s` poller warning. Two 16-document retains ingested 4 and 6 documents in 51 minutes. This is an infrastructure fault unrelated to errand, but it is why the comparison uses `chunks` mode and why the open question above is still open.
