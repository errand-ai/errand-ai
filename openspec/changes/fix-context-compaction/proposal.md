## Why

Context compaction has never once succeeded in production. Fourteen days of `app="task-runner"` logs in Loki account for every attempt:

| Outcome | Count |
|---|---|
| Timed out (`openai.APITimeoutError`) | 6 |
| Returned an empty summary | 13 |
| **Succeeded** | **0** |

Every time a conversation has reached the context ceiling, errand has silently fallen back to `_trim_context_window`, which amputates the oldest messages. The model loses the front of the conversation and starts repeating failed operations — the behaviour reported as "gemma-4 getting stuck". The originally suspected cause (a model overflowing its context window) was ruled out: gemma-4 26B is served by LM Studio with a 260,352-token window, comfortably above the 150,000-token trigger.

Two distinct failure modes, on different model types:

- **Timeout** (task `7ac701a8`, `nemotron-3-ultra-550b-a55b:free`). `COMPACTION_TIMEOUT_SECONDS` defaults to 30s while the call must generate up to `max_tokens=2048`. A free-tier 550B endpoint cannot do that in 30s. Confirmed by traceback: `httpcore.ReadTimeout` → `httpx.ReadTimeout` → `openai.APITimeoutError`.
- **Empty summary** (task `e608f5e6`, `qwen3.6-35b-a3b-ud-mlx`). The call *completes* in ~12s — almost exactly the time to generate 2048 tokens on a 3B-active MoE — and returns empty `.content`. The budget was consumed by tokens that never reached the content field, the expected signature of a reasoning model whose thinking exhausts `max_tokens` before it emits a summary.

Two structural bugs then convert a single failure into a per-turn tax:

- `_trim_context_window` stops the instant the estimate is `<= MAX_CONTEXT_TOKENS`, leaving zero headroom, so the next tool result re-crosses the threshold immediately.
- There is no backoff. `_compact_context` runs from `filter_model_input` on every model call, so a compaction that failed seconds ago is retried in full on the next turn.

The result is a spiral, visible in the timestamps for task `e608f5e6`: failures 9–11 minutes apart at first, tightening to every ~12 seconds, each one burning a model call and discarding more history.

Underlying all of it: the compaction spec describes only the success path. No requirement covers what happens when compaction fails, so nothing failed when it never worked. This is the same gap that let a stubbed `save()` ship in `litellm-mcp-settings-ui`.

## What Changes

- **Make the compaction call configurable rather than fixed at deploy time.** `compaction_model`, `compaction_timeout` and `compaction_max_tokens` become settings resolved server-side and injected into the runner, replacing hard-coded defaults and deploy-time env vars. Env vars remain as overrides, matching the existing settings precedence.
- **Give the trim fallback headroom.** Trim to a target well below the ceiling rather than to the ceiling itself, so a single fallback does not guarantee an immediate re-trigger.
- **Back off after a failed compaction** so a failing configuration costs one attempt, not one per turn.
- **Log why compaction produced nothing.** On the empty-summary path, record `finish_reason`, content length and whether a reasoning/thinking field was populated — the information needed to distinguish "model refused" from "thinking consumed the budget".
- Raise the default compaction timeout from 30s, which is unachievable for any local or free-tier model generating 2048 tokens.

**Not in scope**: surfacing context usage in the UI or to Loki — that is the follow-on `context-usage-visibility` change. This change is deliberately limited to making the mechanism work, and can ship without it.

## Capabilities

### New Capabilities

None. This repairs behaviour that is already specified, and specifies the failure path that was omitted.

### Modified Capabilities

- `task-runner-context-compaction`: replace the env-var-only "Compaction model configuration" requirement with settings-based resolution covering model, timeout and max tokens; add requirements for failure handling (backoff), and for diagnostics on the empty-summary path.
- `agent-context-management`: modify "Context window trimming" so the trimmer targets a level below `MAX_CONTEXT_TOKENS` rather than stopping at it.
- `settings-registry`: register the three new keys. `compaction_model` must be added to `MODEL_SETTING_KEYS` or it will hit the `model`/`model_id` mismatch fixed in `selective-mcp-server-defaults`.

The Task Management tab exposure is **not** an errand spec change: `admin-settings-ui` specifies which cards compose `/settings/tasks`, not which fields each card renders, and that composition is unchanged. The form fields belong to `TaskManagementCard` in `@errand-ai/ui-components` and are specified in that repo.

## Impact

- **Code**: `task-runner/main.py` (`_compact_context`, `_trim_context_window`, backoff state), `errand/settings_registry.py` (three keys, `MODEL_SETTING_KEYS`), `errand/task_manager.py` (inject the resolved values into the runner env).
- **Library dependency**: the Task Management tab is `TaskManagementCard` / `LlmModelCard` from `@errand-ai/ui-components`, so the *form fields* require a library release plus a consumer bump. The settings themselves are server-side and settable via `PUT /api/settings` without any library change — so the fix can land and be configured before the UI catches up. Task ordering should reflect that.
- **Deployment**: no schema or migration change. New settings default to values that work; existing deployments improve without operator action.
- **Risk**: low and strictly improving — compaction currently has a 0% success rate, so any change is measured against a floor of total failure. The main risk is choosing a default timeout so generous that a genuinely hung compaction call stalls a task; backoff bounds that to one occurrence.
- **Verification**: the failure signatures are queryable. `{app="task-runner"} |= "Context compaction"` in Loki, filtered by `content_manager_task_id`, gives a direct before/after. Note the runner runs at `WARNING` in production, so `logger.info` diagnostics will not appear — new diagnostics must be `WARNING`+ or structured events, which bypass log-level filtering entirely because `emit_event` uses `print`, not the logger.
