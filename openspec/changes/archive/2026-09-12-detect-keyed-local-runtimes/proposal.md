## Why

`local-ai-provider-detection` shipped a scan that finds local AI runtimes and registers what answers. It misses any runtime that requires an API key, which is not a corner case — vLLM takes `--api-key`, and oMLX requires one by default.

The failure is invisible in the way that matters. On a machine running oMLX on port 8000 — a candidate port the scan already probes — the scan reports it found only Ollama. Nothing errors. The user is simply told their local AI is not there:

```
host.docker.internal:8000/v1/models   401  {"error":{"message":"API key required"}}   ← skipped
host.docker.internal:11434/v1/models  200                                              ← found
```

`probe_provider_type()` accepts only HTTP 200, so a 401 resolves to `unknown` and the candidate is discarded. That contradicts the requirement already in `openspec/specs/llm-providers/spec.md`, whose scenario reads *"WHEN a scan is run and an OpenAI-compatible service **answers** on a candidate endpoint THEN a provider is created for it"*. It answered.

The rule that was missing is one the same change already relies on elsewhere: its own task 6.1 verified all eighteen catalog base URLs by treating **401 or 403 as proof the endpoint exists**, and 404 or DNS failure as proof it does not. Detection never applied it.

Two further defects surfaced alongside it, both cheap to fix here and awkward to fix separately:

- **A keyed service cannot be identified.** `identify_runtime()` reads `owned_by` from the model listing. A 401 yields no body, so identification falls through to the port — registering an oMLX server on 8000 as `vllm`. The rule that identification comes from the response, not the port, exists precisely to prevent that.
- **errand publishes on a candidate port.** Both compose files publish the server on host `8000`, which is also the `vllm` candidate. A user running a local OpenAI-compatible server on the conventional port cannot run errand's default compose beside it — and that user is exactly who local detection was written for. This bit during verification: the host port was shadowed and errand's own API became unreachable from the host.

## What Changes

- **A 401 or 403 from a candidate endpoint means "a service is here that needs a key"** — reported by the scan as such, in its own right, distinct from both "found" and "nothing there".
- **The scan does not invent a provider for it.** A row carrying the `sk-no-key-required` sentinel against a service that rejects it would be a provider guaranteed to fail. The user supplies the key, and adoption creates the provider.
- **Adoption probes with the supplied key and takes the runtime's name from the answer** — so naming happens at the first moment the response can actually be read, rather than being guessed from a port number beforehand.
- **A re-scan probes an already-adopted provider with its own stored key**, so a keyed runtime that is present and working is not mistaken for one that has gone away and reconciled out from under the user.
- **A response that could not be read never yields a runtime name.** Falling back to the port is reasonable when a body was read and carried no marker; it is a guess presented as a fact when no body was read at all.
- **errand's published host port becomes configurable**, defaulting to 8000 so no existing deployment changes.

## Capabilities

### Modified Capabilities

- `llm-providers` — 401/403 recognised as a keyed service; adoption with a caller-supplied key; reconciliation that probes adopted providers with their own key.
- `llm-provider-settings-ui` — scan results present keyed runtimes with a way to supply a key and adopt them.
- `local-dev-environment` — the published server port is configurable.

## Non-goals

- **Changing `probe_provider_type()`'s contract.** It answers "what type is this provider", and `unknown` is the right answer for an endpoint that will not talk to us. Detection needs a different question — "is something OpenAI-compatible here" — and asks it separately rather than loosening a probe that four other call sites depend on.
- **Storing a key the user did not supply.** No sentinel, no blank, no guess.
- **Discovering the key.** errand does not read runtime config files, environment variables of other processes, or anything else on the host to find a key it was not given.
- **Changing the default published port.** It stays 8000; only the ability to override it is new.
