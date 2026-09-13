## Context

A newly installed errand has a working provider and no usable model, and says nothing about it. Measured on a clean stack with Ollama detected and default:

```
POST /api/tasks {"input": "..."}   →  201, status "review", tags ["Needs Info"]
```

Two independent mechanisms produce that, and both must change or the symptom persists:

```
llm_model unset            →  generate_title success=False  →  "Needs Info"  →  review
                              (TaskManager only takes `pending`, so it never runs)

task_processing_model unset →  DEFAULT_TASK_PROCESSING_MODEL, provider_id None
                              →  OPENAI_BASE_URL/API_KEY empty  →  runner exits
```

The second is worth stating plainly: `DEFAULT_TASK_PROCESSING_MODEL = "claude-sonnet-4-5-20250929"` is an Anthropic model name used as the fallback on an OpenAI-compatible path, applied with no provider. It cannot succeed on any installation that reaches it.

## Decisions

### D1 — `Needs Info` describes the input, never the installation

Routing splits on whether the classifier produced an answer, not on whether the call returned successfully.

| what happened | tag | status |
|---|---|---|
| classifier answered, no usable description | Needs Info | review |
| no model configured | — | by category (`immediate` → pending) |
| configured provider gone | — | by category |
| request could not be completed | — | by category |

The user-visible test is whether editing the task could fix it. A task parked because the input was thin is repairable by the person who wrote it. A task parked because nobody was asked is not, and the tag sends them to edit text that was never the problem.

The short-input rule (≤ 5 words → review) is deliberately untouched. There the classifier is *not run on purpose*, which is a product judgement about the input, not a failure to reach anything.

### D2 — The cause travels in the result, not re-derived by the caller

`generate_title` reports whether an attempt was made. The alternative — `create_task` re-reading `llm_model` to work out why — duplicates the resolution rule (`resolve_model_setting` also treats a departed provider as unset) and races the state it describes.

### D3 — No model is chosen by guessing

Measured against a real runtime's `/v1/models`:

```
fields present: created, id, max_model_len, object, owned_by      ← no mode

[0] Qwen3.8-27B-MLX-4bit          [4] Qwen3-Embedding-0.6B-4bit-DWQ
[1] Qwen3.8-27B-MLX-8bit          [5] Qwen3-Reranker-4B-mxfp8
[2] GLM-4.7-Flash-MLX-8bit        [9] whisper-large-v3-turbo
```

Chat, embedding, reranker and speech in one undifferentiated list. First-listed is a coin flip that another runtime's ordering answers with `whisper-large-v3-turbo`, and `llm-providers` already rejects the naming heuristic that would exclude the rest, because a substring check for `embed` misses `bge-m3`. `model-metadata-registry` knows nothing about identifiers of this shape — `mode` came back null for every model on every local runtime measured.

Exactly one model is not a guess: there is nothing to choose. Everything else is the user's to say.

### D4 — Probing for a chat-capable model was rejected on cost, not principle

Sending a one-token completion to each candidate and keeping the first that answers is a *reliable* signal, and it is the rule this codebase applies elsewhere — the response is the authority, not the name or the port. It is rejected here because of what the request does on a local runtime: it loads model weights. That is minutes and, measured on the verification machine, ~17 GB of RAM for a 27B model, incurred at first run, possibly several times before a chat model is found. `DETECTED_PROVIDER_LLM_TIMEOUT` is 300 seconds precisely because a first request to a local runtime behaves this way.

A first-run convenience that may take ten minutes and evict the user's memory is worse than a dropdown.

### D5 — The scan is where the question is asked

The question needs a moment where a provider exists, its listing is one call away, and the user is present and expecting an answer. The scan is the only such moment; every other path (settings deep-link, a banner, a first-task interstitial) either interrupts something else or arrives after the user has already been failed.

So the scan result grows what a caller needs to ask: which provider was registered, and whether a model is configured. The scan does not itself prompt — it reports, and the settings card asks. That keeps the decision on the client where the user is, and keeps the server free of UI sequencing.

### D6 — Establishing settings follows the empty-installation rule that already exists

`llm-providers` says detection claims the default provider *only on an empty installation*, because with nothing configured there is nothing to override. Model settings take the same rule and the same justification. An installation that already has a model keeps it, whatever a later scan finds.

### D7 — The unconfigured state gets a representation

`{"provider_id": null, "model": ""}` is indistinguishable from "never set" and requires a caller to cross-check the provider list to interpret. Both the API and the settings card need a direct answer, including the case that looks configured and is not: a setting naming a provider that has since been deleted.

### D8 — Backend ships alone; the prompt follows

The card lives in `errand-component-library`, so the prompt needs a release there and a pin bump here — the round trip `detect-keyed-local-runtimes` has just been through. The backend half is therefore scoped to stand alone and be worth shipping alone: after it, a first task **runs** instead of parking silently, and the missing model is visible in the API. The prompt turns that from legible into one-click.

Ordering is forced, not chosen: the card cannot ship against a server that does not serve the endpoints it calls.

### D9 — Applying a choice is one operation, not a settings write

`PUT /api/settings` could set `llm_model` and `task_processing_model` today with no new endpoint. It is the wrong shape: it puts the current set of roles into every caller, so adding or renaming one later leaves callers configuring a subset and the remainder silently unset — this change's own defect, reintroduced by the fix for it. It also cannot validate the model against the provider's listing, which is what separates a choice from a typo.

So a caller states which model errand should use, and the server decides which settings implement that. The card never learns the key names.

### D10 — One question, two roles, said out loud

The first-run choice sets both the classification model and the execution model. Setting only one leaves the original defect alive in whichever role was omitted: choose a model and the next task still parks for want of a title model, or still fails at the runner.

Setting both is right, and silently setting both is not. A question that decides more than it appears to is the same fault as guessing a model, approached from the other side — so the UI states what the answer governs. Users who want the two to differ still do that in settings, and saying what the choice covers is also what tells them that is possible.

## Risks

- **A task that now reaches `pending` will fail at the runner** where no model is configured — later than before, but loudly and with a cause, rather than silently parking under a misleading tag. D1 is an improvement in honesty, not a guarantee of success; only choosing a model achieves that.
- **The sole-model case is rare.** Ollama and LM Studio installations typically list several. Most users will see the prompt, which is the intended outcome, but it means the automatic path is a small share of first runs.
- **`DEFAULT_TASK_PROCESSING_MODEL` may be load-bearing somewhere unmeasured.** It is reached only when `task_processing_model` is unset, which is the broken state this change addresses; removing or changing it needs a check for callers that rely on the string.
- **Two settings, one question.** `llm_model` (classification) and `task_processing_model` (execution) are separate settings that a first-run choice sets together. A user who later wants different models for the two must still do that in settings, and nothing here should make that harder.
