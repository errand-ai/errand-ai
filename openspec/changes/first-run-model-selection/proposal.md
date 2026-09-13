## Why

A newly installed errand cannot run a task. Not "runs badly" — cannot run one at all, and does not say so.

`local-ai-provider-detection` and `detect-keyed-local-runtimes` made provider setup work: press **Scan for local AI**, and a runtime is found, registered, and made the default on an empty installation. What neither change did — because neither was about this — is connect a default *provider* to a chosen *model*. Every model setting ships unset, and nothing in the product ever writes one:

```
llm_model default             {"provider_id": null, "model": ""}   settings_registry.py:17
task_processing_model default {"provider_id": null, "model": ""}   settings_registry.py:18
```

The only code that writes either is `_clear_model_settings_for_provider`, which clears them.

Measured on a clean stack with Ollama detected and default:

```
POST /api/tasks {"input": "..."}   →  201, status "review", tags ["Needs Info"]
```

The task never runs. `generate_title` resolves `llm_model`, gets `(None, None)`, and returns `success=False` (`llm.py:164`). `create_task` reads that as missing information and applies **Needs Info** (`main.py:853`), which routes the task to `review` (`main.py:912`). `TaskManager` selects `status == "pending"` and nothing else (`task_manager.py:1003`). A short input (≤ 5 words) takes a different branch to the same place.

Reaching `pending` would not save it. `task_processing_model` falls back to `DEFAULT_TASK_PROCESSING_MODEL = "claude-sonnet-4-5-20250929"` with `provider_id: None` — an Anthropic model name on an OpenAI-compatible path — and with no provider id, `OPENAI_BASE_URL` and `OPENAI_API_KEY` are left empty and the runner exits on missing environment variables.

So the first run is: install, scan, watch errand find your Ollama and mark it default, type your first task, and watch it land in a review column under a tag you have no reason to understand. Nothing anywhere says *choose a model*.

Two distinct defects sit behind that.

**Errand reports its own failure as the user's.** "The classifier said this input is ambiguous" and "there was no classifier to ask" are different facts with the same handling. `Needs Info` means *you did not tell us enough*; it is the wrong thing to say when nobody was asked. This reverses a decision recorded in `task-categorisation`, which states that an LLM call failure routes to `review`. That decision assumed the call failing meant the model tried and could not classify. An unconfigured model was not considered, and it is the state every new installation is in.

**Nobody ever asks which model to use.** A provider is not a model, and errand has no moment in its flow where the question is put. The scan is that moment — the user has just pressed a button, a provider now exists, and its model list is one call away — and it passes in silence.

### The model cannot be chosen automatically

Measured against a real runtime (oMLX, ten models):

```
[0] Qwen3.8-27B-MLX-4bit          [4] Qwen3-Embedding-0.6B-4bit-DWQ
[1] Qwen3.8-27B-MLX-8bit          [5] Qwen3-Reranker-4B-mxfp8
[2] GLM-4.7-Flash-MLX-8bit        [9] whisper-large-v3-turbo

fields present: created, id, max_model_len, object, owned_by
```

There is no `mode` field. Chat, embedding, reranker and speech models arrive in one undifferentiated list, and `model-metadata-registry` knows nothing about identifiers like these. Taking the first is a coin flip that lands on `whisper-large-v3-turbo` for some other runtime's ordering, and `llm-providers` already rules out the obvious patch: *"A name heuristic is not a substitute: a substring check for `embed` misses `bge-m3`."*

So errand asks the user, at the one moment the question is cheap to answer, and stores nothing it had to guess.

## What Changes

- **A task the classifier could not reach is not `Needs Info`.** When the classifier cannot run — no model configured, provider gone, request failed — the task SHALL be created runnable with the fallback title. `Needs Info` keeps its meaning: the classifier ran and the input did not carry enough to act on.
- **The scan asks which model to use.** Where a scan registers a provider on an installation with no model configured, the settings UI presents that provider's models and invites a choice, applying it to the model settings. One click, at the moment the user is already looking at the result.
- **A provider that lists exactly one model needs no question.** There is nothing to choose, so it is chosen.
- **"No model configured" becomes a state errand can state.** The provider settings surface it, and the API exposes it, so the absence is legible rather than inferred from a task that behaved oddly.
- **`DEFAULT_TASK_PROCESSING_MODEL` stops being a hardcoded model name.** A constant naming one vendor's model, applied with no provider, cannot succeed on any installation that reaches it; it yields an empty base URL and a runner that exits on missing environment variables. It must fail legibly or not be reached.

## Capabilities

### Modified Capabilities

- `task-categorisation` — an unreachable classifier no longer yields `Needs Info`; the "LLM failure goes to review" scenario is split by cause.
- `llm-integration` — `generate_title` reports *why* it failed, so the caller can route on it.
- `llm-providers` — model settings are established when a scan registers a provider on an installation with none, either from the sole model or from a caller-supplied choice; the unconfigured state is exposed.
- `llm-provider-settings-ui` — the scan panel asks for a model and applies it.

## Non-goals

- **Guessing a model.** No name heuristics, no first-listed, no vendor default. This change stores a model the user chose or a runtime that offers exactly one, and nothing else — the same restraint `detect-keyed-local-runtimes` applied to API keys.
- **Probing models to discover which can chat.** A one-token completion is a reliable signal and the wrong price: on a local runtime it loads weights, which is minutes and gigabytes at first run. The 300-second detected-provider timeout exists because of that cost.
- **Improving classification of genuinely ambiguous input.** That is `interactive-task-spec`. This change is its prerequisite, not its substitute: a clarification loop is also an LLM call and also cannot run on a fresh installation.
- **Changing what `Needs Info` means** where the classifier did run. Those tasks keep routing to `review`.
- **Choosing a transcription or compaction model.** Only the two settings that block a first task are in scope.

## Impact

- `errand/llm.py` — `generate_title` result shape.
- `errand/main.py` — `create_task`'s handling of a classifier that could not run; scan/model-selection surface.
- `errand/llm_providers.py` — `resolve_model_setting`; establishing settings alongside a first provider.
- `errand/local_ai_detection.py` — the scan's empty-installation path.
- `errand/task_manager.py` — `DEFAULT_TASK_PROCESSING_MODEL` and the provider resolution that leaves `OPENAI_BASE_URL` empty.
- `errand/settings_registry.py` — defaults for the two model settings.
- **Cross-repo**: `errand-component-library`'s `LlmProviderCard` scan panel, then a pin bump and a seam-test shape here. The backend ships and is useful without it — the silent parking stops either way.
- No migration expected: these are settings rows with defaults, not schema.
