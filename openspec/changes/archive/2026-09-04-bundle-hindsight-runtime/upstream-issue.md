# Upstream issues for `vectorize-io/hindsight`

Both were filed on 2026-09-04:

- https://github.com/vectorize-io/hindsight/issues/4116 — the `transformers` packaging gap
- https://github.com/vectorize-io/hindsight/issues/4118 — `pg_trgm` unusable in schema mode

Kept here as the record of what was reported and the evidence behind it.

---

## Filed: https://github.com/vectorize-io/hindsight/issues/4116

**Title:** `slim` image ships the ONNX embeddings stack but cannot initialise it — `transformers` is missing

**Body:**

## Summary

`ghcr.io/vectorize-io/hindsight-api:0.9.2-slim` contains everything
`OnnxEmbeddings` needs except `transformers`, so
`HINDSIGHT_API_EMBEDDINGS_PROVIDER=onnx` cannot be used with the published slim
image. Adding one pure-Python dependency would make slim self-sufficient for
local embeddings.

## What the slim image already ships

```
$ docker run --rm --entrypoint sh ghcr.io/vectorize-io/hindsight-api:0.9.2-slim \
    -c '/app/api/.venv/bin/python -c "
import importlib.metadata as md
for p in [\"onnxruntime\",\"tokenizers\",\"huggingface_hub\",\"transformers\"]:
    try: print(p, md.version(p))
    except Exception: print(p, \"ABSENT\")
"'
onnxruntime 1.20.1
tokenizers 0.22.2
huggingface_hub 1.6.0
transformers ABSENT
```

`onnxruntime` alone is ~32 MB of the image. `hindsight_api/engine/embeddings.py`
(`OnnxEmbeddings`) and `hindsight_api/engine/cross_encoder.py`
(`FlashRankCrossEncoder`) are both present in the package.

## What fails

`OnnxEmbeddings.initialize()` raises immediately:

```python
try:
    import onnxruntime as ort
    from transformers import AutoTokenizer
except ImportError as exc:
    raise ImportError(
        "onnxruntime and transformers are required for OnnxEmbeddings. "
        "Install with: pip install 'hindsight-api-slim[local-onnx]'"
    ) from exc
```

`onnxruntime` imports fine; `transformers` does not. The tokenizer is the only
thing `transformers` is used for here — `AutoTokenizer.from_pretrained(...)` at
the end of the same method.

The suggested remedy in the error message,
`pip install 'hindsight-api-slim[local-onnx]'`, is not straightforwardly
actionable inside the published image: the virtual environment at
`/app/api/.venv` has no `pip` executable (installing requires
`VIRTUAL_ENV=/app/api/.venv uv pip install ...`).

## Why this matters

The practical effect is that slim cannot embed locally at all. Every remaining
option (`tei`, `openai-compatible`, `litellm`, …) requires an external
embeddings endpoint, which is a significant extra ask for anyone whose reason
for choosing slim was to avoid the torch-based full image.

Measured on arm64: `uv pip install transformers==5.16.1 flashrank==0.2.10` into
`/app/api/.venv` pulls **no torch and no sentence-transformers**, and adds a
70 MB layer — 2.90 GB to 2.97 GB, about 2%, against 5.47 GB for the full image.
(The resolver also adds `safetensors` and upgrades the bundled `tokenizers`
0.22.2 → 0.23.2. Constraining to `transformers<5` avoids that but is worse: it
downgrades `huggingface-hub` 1.6.0 → 0.36.2, which the image itself uses.)

## Suggested fix

Include `transformers` (and, for the reranker, `flashrank`) in the slim image,
or document that `local-onnx` is a build-time extra the published slim image
does not carry.

## Environment

- Image: `ghcr.io/vectorize-io/hindsight-api:0.9.2-slim`
  (digest `sha256:7635a15739361dbdf221ba796ad25a813f876144fe113022eea8e26cb6ee75e7`,
  identical to `latest-slim`)
- Platform: linux/arm64, Docker 28.4.0

---

## Filed: https://github.com/vectorize-io/hindsight/issues/4118

`pg_trgm` created in the tenant schema is unusable at runtime. Found while
implementing this change; unrelated to the `transformers` gap above.

**Title:** In schema mode, `pg_trgm` is created in the tenant schema where the runtime cannot resolve `%`, and retain fails silently forever

**Body:**

## Summary

With `HINDSIGHT_API_DATABASE_SCHEMA` set to a non-`public` schema, Hindsight's
own migration creates `pg_trgm` **inside that schema**. Its runtime then cannot
resolve the `%` operator, so every `retain` fails during entity resolution and
retries indefinitely. Nothing surfaces the failure to the caller.

## Reproduction

1. Point Hindsight at a PostgreSQL database with `HINDSIGHT_API_DATABASE_SCHEMA=hindsight`.
2. Start it against an empty database and let its migrations run.
3. Call the MCP `retain` tool with any content.

Observed on `0.9.2-slim`, PostgreSQL 18 (`pgvector/pgvector:pg18`), linux/arm64.

## What happens

`CREATE EXTENSION pg_trgm` lands in the tenant schema:

```
$ psql -tAc "select e.extname, n.nspname from pg_extension e
             join pg_namespace n on n.oid = e.extnamespace"
pg_trgm|hindsight
vector|public
```

Every background retain then fails:

```
ERROR - hindsight_api.engine.memory_engine - Task execution failed: batch_retain,
  error: UndefinedFunctionError: operator does not exist: text % text
HINT:  No operator matches the given name and argument types.
  File "hindsight_api/engine/entity_resolver.py", line 773, in _resolve_entities_batch_trigram
  File "asyncpg/protocol/protocol.pyx", line 165, in prepare
WARNING - hindsight_api.worker.poller - Task ... scheduled for retry at ...
```

The retry repeats on a one-minute backoff and never succeeds.

Operator resolution measured directly, with the extension in `public`:

| `search_path` | `SELECT 'abc' % 'abd'` |
|---|---|
| `hindsight` | fails |
| `public` | resolves |
| `hindsight, public` | resolves |

## Why it is hard to notice

The failure is invisible from every direction a user would look:

- the container is **healthy**, and `/health` returns 200;
- the MCP `retain` call returns `{"status":"accepted","operation_id":"..."}`, so
  an agent reports success;
- only the asynchronous `batch_retain` fails, and it fails into the log.

The single observable symptom is that memory never appears. On our first
schema-mode deployment this looked like an LLM extraction problem for some time.

## Note on `vector`

Interestingly, `vector` is handled correctly: if it is found outside `public`,
Hindsight relocates it —

```
WARNING - hindsight_api.migrations - pgvector extension found in schema 'hindsight'
  instead of 'public'. Attempting to relocate...
INFO - hindsight_api.migrations - pgvector extension relocated to public schema
```

`pg_trgm` appears to be missing the equivalent treatment.

## Workaround

Pre-create the extension in `public` before Hindsight first connects. This works
because `CREATE EXTENSION IF NOT EXISTS` matches on the database rather than the
schema, so it makes Hindsight's own mis-placed create a no-op:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

## Suggested fix

Create `pg_trgm` in `public` explicitly, or relocate it on start-up as pgvector
already is.
