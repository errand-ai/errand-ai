## Why

On Kubernetes, a completed task's stored logs are the **Python `repr` of a bytes object** — `b'Collecting google-genai…\n…'` — with zero real newlines. The log viewer splits on `\n`, gets one enormous line, fails to parse it as JSON, and falls back to flat rendering. Live streaming is unaffected, so the same task looks correct while running and raw once finished. Measured on production: **26 of 28 tasks with logs are affected**. The same corrupted string is what the `task_logs` MCP tool returns, so this is not only a display problem.

## Root cause

`errand/container_runtime.py:694`:

```python
full_logs = self.core_v1.read_namespaced_pod_log(pod_name, namespace)
```

This is the **only** `read_namespaced_pod_log` call in the file without `_preload_content=False`. With preloading on, the kubernetes client deserialises the response into the declared `str` type:

```python
# kubernetes/client/api_client.py — deserialize()
try:
    data = json.loads(response.data)   # response.data is BYTES
except ValueError:
    data = response.data               # ...so it stays BYTES

# __deserialize_primitive()
return klass(data)                     # str(b'...') == "b'...'"
```

Pod logs are never valid JSON, so `json.loads` always raises, `data` stays bytes, and `str(bytes)` produces the repr. Reproduced directly against the installed client (kubernetes 36.0.2, urllib3 2.6.3): a realistic pod-log payload comes back as a `str` with **0 real newlines and 3 literal `\n`**, and its first `split("\n")` element fails `JSON.parse`.

The defect is in the client library, not in errand — which is why searching errand for `str(bytes)` finds nothing and the original report's lead went cold.

### Why live streaming is unaffected

| Path | Call | Result |
|---|---|---|
| Live (`:643`, `:809`) | `read_namespaced_pod_log(..., _preload_content=False)` | raw stream; errand calls `chunk.decode("utf-8", errors="replace")` itself → real newlines |
| Stored (`:694`) | `read_namespaced_pod_log(pod_name, namespace)` | preloaded → `str(bytes)` → repr |

One keyword argument separates them.

### Why it has never been seen locally

`DockerRuntime.result()` decodes explicitly (`container_runtime.py:328-329`). Local docker-compose is therefore correct, and the bug appears only under `CONTAINER_RUNTIME=kubernetes`. Anyone reproducing locally will conclude the code is fine.

## What Changes

- Read pod logs in `KubernetesRuntime.result()` without preloading and decode explicitly, matching what `run()` already does. Both paths then obtain text the same way.
- Add a regression test asserting the returned logs contain **real newline characters and no `b'` prefix**. Asserting "logs are non-empty" would pass today and is what let this through.
- Repair the 26 already-corrupted rows with a one-off backfill. They are mechanically recoverable — a `b'...'` repr round-trips through `ast.literal_eval` — and leaving them corrupt means the fix appears not to work for every task that already exists.
- Record in `container-runtime` that a runtime returns decoded text, so the contract is stated rather than assumed.

**Not in scope:**

- Pinning `kubernetes>=36.0.2,<37`. A floating range on a library whose deserialisation behaviour produced this is a fair concern, but it belongs with the constraints-file question rather than here.
- Changing the log viewer to tolerate the repr. The data is wrong; making the reader compensate would hide the defect permanently and still leave the MCP tool broken.
- The errand-cloud `{taskId}` template-literal bug (reportedly fixed in its PR #69). That one broke errand-cloud's *live* streaming and is unrelated to this defect. Note this change **does** fix errand-cloud's raw-rendering bug — see below.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `container-runtime`: gains a requirement that pod logs are returned as decoded text with real line breaks. The existing "KubernetesRuntime creates Jobs and ConfigMaps" requirement says `result` reads "the full pod logs as stderr" but says nothing about encoding, which is precisely the gap that allowed a bytes repr to satisfy it.

## Impact

- **Code**: `errand/container_runtime.py` (one call site), a regression test, and a data migration under `errand/alembic/`.
- **Data**: the backfill rewrites `tasks.runner_logs` for affected rows. It is a content repair, not a schema change, and it is one-way — the migration must be conservative about what it treats as corrupt.
- **Fixes without further work, in this repo**: the `task_logs` MCP tool (`mcp_server.py:421-424`), which returns `runner_logs` verbatim.
- **Fixes errand-cloud with no change in that repository.** Verified against the checkout: `frontend/cloud/src/views/TaskBoard.vue:229` binds `:log-data="…runner_logs…"` — byte-identical to errand's own `KanbanBoard.vue:163` — and pins the same `@errand-ai/ui-components` 0.18.0, so the same parser. Its proxy is a verbatim body passthrough (`app/api/proxy.py:79`, `Response(content=result.get("body", ""))`) with no re-serialisation. errand-cloud is a downstream reader of the same field: repair the field and it renders, historical tasks included once the backfill runs.
- **Unblocks**: per-turn context usage on completed tasks. `llm_turn_end` events carrying `input_tokens`/`output_tokens` are currently entombed in the repr, so the turn badge from `@errand-ai/ui-components` ≥0.18.0 renders only during live streaming and never afterwards.
- **Not a regression from any recent change**: the affected line has been unchanged since `ca51cbc` (2026-02-22). The two healthy production tasks are the oldest (88d, 119d); everything from 44d onward is corrupt.
