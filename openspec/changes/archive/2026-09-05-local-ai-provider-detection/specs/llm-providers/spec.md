## ADDED Requirements

### Requirement: Host gateway address is a deployment fact

The server SHALL read the address by which it can reach services on the container host from a `HOST_GATEWAY_ADDRESS` environment variable, defaulting to `host.docker.internal`. When the variable is explicitly set empty, or the container runtime is Kubernetes, local AI detection SHALL be treated as unavailable.

#### Scenario: Default gateway address

- **WHEN** `HOST_GATEWAY_ADDRESS` is not set
- **THEN** the server uses `host.docker.internal` when probing for host-run AI services

#### Scenario: Explicit gateway address

- **WHEN** `HOST_GATEWAY_ADDRESS` is set to a runtime-specific address
- **THEN** the server probes host-run AI services at that address

#### Scenario: Detection unavailable on Kubernetes

- **WHEN** the container runtime is Kubernetes
- **THEN** local AI detection reports itself unavailable
- **AND** no probe requests are made

### Requirement: Local AI detection

The server SHALL provide an operation that probes a fixed set of well-known local AI endpoints through the host gateway address and registers those that respond as LLM providers. Detection SHALL use the existing provider type probe. Candidate endpoints SHALL be a fixed enumeration; the server SHALL NOT scan port ranges. Services SHALL be identified by their probe response, not by the port they answered on, because several runtimes share a default port.

#### Scenario: Responding runtime is registered

- **WHEN** a scan is run and an OpenAI-compatible service answers on a candidate endpoint
- **THEN** a provider is created for it with the base URL that answered
- **AND** its provider type is set from the probe result

#### Scenario: Stored URL is the URL that answered

- **WHEN** a service is detected through the host gateway address
- **THEN** the stored base URL uses that gateway address, not `localhost`

#### Scenario: No port scanning

- **WHEN** a scan runs
- **THEN** only endpoints in the fixed candidate enumeration are contacted

#### Scenario: Shared default port disambiguated by response

- **WHEN** two candidate runtimes share a default port and a service answers there
- **THEN** the registered provider reflects what the probe response identified, not an assumption from the port number

#### Scenario: Nothing running

- **WHEN** a scan runs and no candidate endpoint responds
- **THEN** no providers are created
- **AND** the operation reports that nothing was found, rather than failing

### Requirement: Detected providers are marked and reconciled

Providers created by local detection SHALL carry `source="detected"`. A subsequent scan SHALL upsert those that still respond and remove those that no longer do, following the reconciliation already used for environment-sourced providers. Providers with any other source SHALL NOT be modified or removed by a scan.

#### Scenario: Re-scan updates rather than duplicates

- **WHEN** a scan runs twice against the same responding service
- **THEN** one provider exists for it, updated rather than duplicated

#### Scenario: Departed runtime is reconciled away

- **WHEN** a previously detected service no longer responds and a scan runs
- **THEN** its detected provider is removed

#### Scenario: Manually configured providers untouched

- **WHEN** a scan runs and a manually configured provider exists
- **THEN** that provider is neither modified nor removed

### Requirement: Detection sets a default only on an empty installation

A scan SHALL mark a detected provider as the default only when no LLM provider exists at all. When any provider already exists, detected providers SHALL be registered without altering which provider is default.

#### Scenario: First provider becomes default

- **WHEN** no providers exist and a scan detects one
- **THEN** it is registered and marked as default

#### Scenario: Existing default preserved

- **WHEN** at least one provider already exists and a scan detects another
- **THEN** the detected provider is registered
- **AND** the existing default is unchanged

### Requirement: Provider catalog

The server SHALL expose a catalog of known hosted LLM providers for selection when adding a provider. Each entry SHALL carry a display name, a base URL, whether the provider supports model listing, and a reference to where its API key is obtained. The catalog SHALL include an entry representing an unlisted OpenAI-compatible provider, for which the base URL is supplied by the caller.

#### Scenario: Catalog offered for selection

- **WHEN** the provider catalog is requested
- **THEN** the response lists known providers with their display name, base URL and model-listing support

#### Scenario: Creating from a catalog entry

- **WHEN** a provider is created by selecting a catalog entry and supplying an API key
- **THEN** the provider is created with the catalog entry's base URL
- **AND** its type is probed exactly as for a manually entered provider

#### Scenario: Unlisted provider

- **WHEN** a provider is created using the unlisted OpenAI-compatible entry
- **THEN** the caller supplies both the base URL and the API key
- **AND** the provider is created and probed with those values

#### Scenario: Provider without model listing

- **WHEN** a catalog entry declares that it does not support model listing
- **THEN** that fact is exposed to the caller so a model can be entered directly rather than chosen from a list

### Requirement: Detected providers take a longer default request timeout

A local runtime's first request can spend a long time loading model weights before producing any output. When the provider resolved for a task carries `source="detected"` and no request timeout is specified by either the task profile or the global task-processing timeout setting, the server SHALL use a longer default than it uses for other providers. An explicitly configured timeout at either level SHALL take precedence over this default.

#### Scenario: Detected provider with no configured timeout

- **WHEN** a task resolves a provider created by local detection and neither the task profile nor the global setting specifies a request timeout
- **THEN** the task runner receives the longer default timeout rather than the standard one

#### Scenario: Profile timeout wins

- **WHEN** a task resolves a detected provider and its task profile specifies a request timeout
- **THEN** the profile's value is used

#### Scenario: Global setting wins

- **WHEN** a task resolves a detected provider, its profile specifies no timeout, and the global task-processing timeout setting is configured
- **THEN** the setting's value is used

#### Scenario: Other providers unchanged

- **WHEN** a task resolves a provider that was not created by local detection and no timeout is configured
- **THEN** the standard default timeout is used

### Requirement: Provider reachability can be re-checked

The server SHALL expose a way to re-check whether a configured provider is currently reachable, so that a provider whose backing service has stopped can be distinguished from one that is working. The check SHALL NOT alter stored provider configuration.

#### Scenario: Reachable provider

- **WHEN** a reachability check runs against a responding provider
- **THEN** it reports the provider as reachable

#### Scenario: Unreachable provider

- **WHEN** a reachability check runs against a provider whose service is not responding
- **THEN** it reports the provider as unreachable
- **AND** the stored provider configuration is unchanged

## MODIFIED Requirements

### Requirement: Per-provider model listing
The backend SHALL expose `GET /api/llm/providers/{id}/models` requiring the `admin` role. The endpoint SHALL return a sorted JSON array of model objects, each carrying the model's ID and its resolved mode.

For `litellm` providers: call `AsyncOpenAI(base_url, api_key).models.list()` and return sorted model IDs. If query parameter `mode` is provided (e.g. `?mode=audio_transcription`), additionally query `{stripped_base_url}/model/info` for the provider's own mode for each model.

For `openai_compatible` providers: call `AsyncOpenAI(base_url, api_key).models.list()` and return sorted model IDs. Mode filtering SHALL apply to these providers too, resolved from the model metadata registry, so that a provider whose listing carries no mode is not left unfilterable.

A model's mode SHALL be the one the provider reports where it reports one, and the registry's otherwise. When a `mode` filter is applied, models whose mode is unknown to both the provider and the registry SHALL be returned alongside the matching ones and reported with a null mode, so that a caller can still select a model the registry does not know — rather than being shown an empty list.

For `unknown` providers: return HTTP 404 with `{"detail": "Provider does not support model listing"}`.

#### Scenario: List models from LiteLLM provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` for a LiteLLM provider
- **THEN** the response is a sorted JSON array of models from `models.list()`

#### Scenario: List transcription models from LiteLLM provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models?mode=audio_transcription` for a LiteLLM provider
- **THEN** the response contains the models whose `model_info.mode` is `audio_transcription`
- **AND** models whose mode neither the provider nor the registry knows, which are reported with a null mode

#### Scenario: List models from OpenAI-compatible provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` for an OpenAI-compatible provider
- **THEN** the response is a sorted JSON array of models, each carrying its resolved mode

#### Scenario: List models from unknown provider
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` for an unknown provider
- **THEN** the backend returns HTTP 404

#### Scenario: Provider not found
- **WHEN** an admin sends `GET /api/llm/providers/{id}/models` with a non-existent provider ID
- **THEN** the backend returns HTTP 404
