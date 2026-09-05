## Why

errand has always promoted a full LiteLLM proxy as the way to reach models. For the audience errand is now aiming at — errand-desktop, and Linux users running docker compose — that is overkill and an obstacle. Standing up a proxy, configuring a model list and minting keys is a substantial piece of infrastructure work before the first task can run.

It is also unnecessary, because **errand is already OpenAI-compatible-native**. The inference path is `AsyncOpenAI(base_url=provider.base_url, api_key=...)`; `litellm` is one value of `provider_type` alongside `openai_compatible` and `unknown`; and `llm_providers` is already a multi-row table with a default, so the aggregation the proxy was providing is already in the data model. What the proxy still uniquely offers is virtual keys, cost governance and the MCP gateway — all advanced concerns.

Three things are missing to make the proxy genuinely optional:

1. **No way to pick a provider without knowing its URL.** Adding a provider today means typing a base URL. A user who wants "the one everybody uses" has nothing to click.
2. **No local AI support worth the name.** Ollama, LM Studio, llama.cpp and the MLX servers all expose OpenAI-compatible `/v1/models`, so `probe_provider_type()` already classifies them correctly. errand simply never looks.
3. **Containers cannot reach the host.** Neither compose file declares `extra_hosts`, and `DockerRuntime` falls back to `network_mode="host"` when `TASK_RUNNER_NETWORK` is unset. A locally-detected `http://localhost:11434/v1` would be valid where it was probed and broken everywhere it is consumed.

The third is the real work. The first two are mostly wiring onto machinery that exists.

### The vantage-point problem

`task_manager.py` passes `provider.base_url` verbatim into the task container. The same string is used by errand-server for model listing and title generation, and — once memory is bundled — by Hindsight. Those consumers do not currently agree on what "the host" means:

```
 errand-server (container)         host.docker.internal   not declared
 task-runner (named network)       host.docker.internal   not declared
 task-runner (network_mode=host)   localhost              different answer
 task-runner (Apple runtime)       vmnet gateway          third answer
 Kubernetes pod                    nothing — there is no host
```

The rule this change adopts: **probe from the consumer's vantage point and store the URL that answered.** No placeholder tokens, no per-consumer rewriting, no schema change — but it requires making the vantage points agree first.

## What Changes

- Declare a host gateway address as a deployment fact (`HOST_GATEWAY_ADDRESS`), defaulting to `host.docker.internal`, injected by compose and by errand-desktop (which already computes the Docker vs Apple vmnet value). Kubernetes leaves it unset, which disables local detection.
- Add `extra_hosts` mapping that name to the host gateway on the errand service, the memory service, and on task containers created by `DockerRuntime`.
- Add a local-AI scan that probes a fixed candidate table through the host gateway, using the existing `probe_provider_type()`, and upserts what answers as providers with `source="detected"` — mirroring the existing `scan_env_providers()` pattern including its stale-row cleanup.
- Add a curated catalog of hosted providers so adding one is a dropdown selection rather than a URL to look up, with an **Other (OpenAI-compatible)** entry that takes a base URL and API key for anything not listed.
- Extend the model metadata registry to carry each model's `mode`, so chat and embedding models can be told apart for providers whose `/v1/models` does not say.
- Recommend an aggregator as the default hosted choice rather than a self-hosted proxy, and reposition LiteLLM as an advanced option rather than the expected path.

## Capabilities

### Modified Capabilities

- `llm-providers` — local detection, `source="detected"`, catalog-driven creation.
- `llm-provider-settings-ui` — provider dropdown, Other (OpenAI-compatible), scan control, health state.
- `model-metadata-registry` — model `mode` extracted and exposed.
- `container-runtime` — task containers can resolve the host gateway.
- `local-dev-environment` — compose declares the host gateway mapping.

## Non-goals

- Removing LiteLLM support. `provider_type="litellm"`, the `litellm_mcp` capability and the MCP gateway all keep working unchanged; only the recommendation changes.
- Local detection on Kubernetes. There is no host to detect; the scan reports nothing and the UI says so.
- Managing local AI runtimes. errand detects and uses them; it does not install, start or stop them.
