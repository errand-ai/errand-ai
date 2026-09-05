## Context

This change makes the LiteLLM proxy optional by filling three gaps: a way to choose a hosted provider without knowing its URL, a way to find local AI runtimes, and a network path that lets containers reach them.

It depends on `bundle-hindsight-runtime` landing first, for a reason that is easy to miss: the recommended aggregator, OpenRouter, is **chat-completions only and exposes no embeddings endpoint**. If the memory service still needed an external embeddings provider, recommending OpenRouter would break memory and force a proxy back into the picture. With embeddings running in-process via ONNX, the memory service needs only a chat endpoint — which local AI and OpenRouter both provide.

Both changes also add requirements to `local-dev-environment`, so `bundle-hindsight-runtime` should be archived before this one is implemented.

## Decisions

### D1 — Probe from the consumer's vantage point; store the URL that answered

The alternative — storing `http://localhost:11434/v1` with a flag and rewriting per consumer — needs a schema change and a rewrite at every injection point, each of which can be forgotten. Probing through the same gateway the consumers use means the stored `base_url` is literally the working URL, for errand-server, the task-runner and the memory service alike.

The price is that the vantage points must agree, which is the `extra_hosts` work below.

### D2 — The gateway address is injected, not inferred

errand-server cannot reliably derive its own runtime topology: Docker uses `host.docker.internal`, Apple Containerization uses a vmnet gateway address. errand-desktop already computes exactly this and calls it `hostGatewayIP`. So the address arrives as `HOST_GATEWAY_ADDRESS`, defaulting to `host.docker.internal`:

```
 compose    relies on the default, with extra_hosts mapping it to host-gateway
 desktop    sets it from its existing hostGatewayIP (Docker or Apple vmnet)
 K8s        leaves it unset, which disables scanning entirely
```

`host-gateway` is supported on Docker Desktop and on Linux from Docker 20.10, so one mechanism serves both compose audiences.

### D3 — `network_mode="host"` is not supported for detected providers

`DockerRuntime` falls back to host networking when `TASK_RUNNER_NETWORK` is unset. That is the one mode where the stored URL would be wrong, since the correct answer there is `localhost`. Rather than carry two URL forms, selecting a `source="detected"` provider requires `TASK_RUNNER_NETWORK` to be set, and fails with an explicit message when it is not. Both shipped compose files already set it, so this affects only hand-rolled setups.

### D4 — Fixed candidate table, never a port sweep

Scanning a range of ports from a server process is the kind of behaviour that trips security review and buys nothing. The scan tries a known list and identifies services by their response, not by the port — necessary anyway, since llama.cpp, LocalAI and some MLX servers all default to 8080.

```
 ollama 11434 · lm-studio 1234 · llama.cpp 8080 · jan 1337
 vllm 8000 · localai 8080 · gpt4all 4891 · mlx 10240
```

Every one of these exposes OpenAI-compatible `/v1/models`, so `probe_provider_type()` classifies them with no per-runtime code.

### D5 — Detection mirrors `scan_env_providers`

That function already establishes the pattern: probe, upsert by name, stamp a `source`, and clean up stale rows carrying that source. Detection uses `source="detected"` and follows it, including the cleanup — a runtime that has gone away should not leave a provider row behind.

### D6 — A detected provider becomes the default only on a truly empty install

Auto-selecting a newly detected provider on an existing deployment would silently redirect inference. So a scan sets the default only when no provider exists at all; otherwise providers are registered and left unselected.

### D7 — Provider catalog with an explicit escape hatch

Adding a provider becomes a dropdown. Each catalog entry carries a display name, base URL, whether it supports model listing, and a link to where its API key is obtained. The final entry is **Other (OpenAI-compatible)**, which reveals base URL and API key fields — so the catalog never becomes a gate on providers it does not list.

Base URLs below were verified empirically: an unauthenticated `GET {base_url}/models` returning 200/401/403 proves the endpoint exists, whereas 404 or DNS failure proves the URL wrong. The codes are the ones re-verified at implementation time; several differ from the first pass (Groq, Together, Hyperbolic and Novita now answer 403 rather than 401/200), which changes nothing — every one of them proves the endpoint is there.

| Provider | Base URL | `/models` | Note |
|---|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | 200 | recommended default; aggregator; **no embeddings endpoint** |
| OpenAI | `https://api.openai.com/v1` | 401 | |
| Anthropic | `https://api.anthropic.com/v1` | 401 | compatibility layer; verify chat completions shape |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | **404** | base URL is right — `/chat/completions` answers 400, only `/models` is absent |
| Groq | `https://api.groq.com/openai/v1` | 403 | |
| Mistral | `https://api.mistral.ai/v1` | 401 | |
| DeepSeek | `https://api.deepseek.com/v1` | 401 | |
| xAI | `https://api.x.ai/v1` | 401 | |
| Cerebras | `https://api.cerebras.ai/v1` | 403 | |
| Together AI | `https://api.together.xyz/v1` | 403 | |
| Fireworks AI | `https://api.fireworks.ai/inference/v1` | 401 | |
| DeepInfra | `https://api.deepinfra.com/v1/openai` | 200 | |
| Perplexity | `https://api.perplexity.ai/v1` | 401 | |
| Hugging Face | `https://router.huggingface.co/v1` | 200 | |
| Nebius | `https://api.studio.nebius.com/v1` | 401 | |
| Novita | `https://api.novita.ai/v3/openai` | 403 | |
| Hyperbolic | `https://api.hyperbolic.xyz/v1` | 403 | |
| SiliconFlow | `https://api.siliconflow.cn/v1` | 401 | `.cn`, not `.com` |
| LiteLLM proxy | operator-supplied | — | advanced |
| Other (OpenAI-compatible) | user-supplied | — | escape hatch |

Two entries need a `supports_model_listing: false` flag rather than being dropped: Gemini's OpenAI-compat surface returns 404 on `/models`, and any provider without listing must fall back to typed model entry. This is why the catalog carries the flag at all.

### D8 — Model `mode` comes from the metadata registry, not a name heuristic

Plain `/v1/models` carries no indication of whether a model embeds. A substring check for `embed` misses `bge-m3` entirely. The registry that `model_metadata.py` already downloads carries a `mode` field per model, and its `_alt_normalize()` already maps Ollama-style `phi4` onto the registry's `phi-4` — the mechanism exists and is already exercised against local model names. Extending `ModelMetadata` with `mode` is the smaller and more correct change.

Where a provider does report mode natively, that answer wins over the registry.

### D9 — Detected providers get a longer default request timeout

Measured on an Apple Silicon machine with fast storage: a 4.7 GB model that had not been loaded since boot answered in **2.45 s**, an effective ~1.9 GB/s; a 13 GB model already in the page cache reached its first chunk in **4.78 s**. Extrapolated, a cold 13 GB load is around 7 s — the existing 30 s default survives it with room to spare *on this class of hardware*.

It does not survive every class. The same 13 GB model on a ~500 MB/s SATA SSD is around 26 s before a single token is generated, and larger weights push straight past the limit. Cold-start latency is the failure mode most likely to make local AI feel broken, and a user meeting it has no way to tell a slow load from a hung request.

So the resolution order in the task manager gains one step: when the resolved provider carries `source="detected"` and **neither** the task profile's `llm_timeout` **nor** the `task_processing_timeout` setting specifies a value, the default becomes 300 s rather than 30 s. An explicit value at either level still wins — this raises a default, it never overrides configuration.

The narrower alternative, separating first-token wait from total request timeout via `httpx.Timeout(read=...)`, is the more correct instrument but changes timeout semantics for every provider rather than only the affected ones. That belongs in a change of its own.

### D10 — Detected providers store `sk-no-key-required` as their API key

`llm_providers.api_key_encrypted` is `NOT NULL`, and local runtimes ignore `Authorization` entirely, so a detected provider needs some value. An empty string is the literally truthful option and the worst one: it sends a bare `Authorization: Bearer` header that some OpenAI-compatible servers reject, trading a harmless untruth in the data model for a real runtime failure.

`sk-no-key-required` is the string llama.cpp, LocalAI and LM Studio use in their own documentation and examples, so it is the value an operator is most likely to already recognise as a placeholder.

### D11 — The aggregator recommendation lives in documentation, not catalog ordering

Encoding a preference in the order of a dropdown states it only to someone who notices the order, and states it permanently — the catalog is data that will be re-verified and extended, and a recommendation embedded in its sequence rots silently. Documentation says it once, explicitly, where a user deciding how to start is already reading.

## Risks

- **Cold-start latency on local models.** A local runtime's first request can spend a long time loading weights before generating anything. Measured and resolved in D9: detected providers take a 300 s default rather than 30 s. The residual risk is that a machine slow enough to exceed even 300 s exists, in which case the per-profile and global timeout settings remain the remedy.
- **Stale detected providers.** A provider row outlives the runtime that was detected. Without a visible health state, the failure surfaces as a confusing task error.
- **Catalog rot.** Base URLs change. Every entry is verified at implementation time, and the "Other" entry means a stale catalog is never a hard block.
- **Large model lists.** An aggregator can return several hundred models; a plain dropdown is unusable at that size.
