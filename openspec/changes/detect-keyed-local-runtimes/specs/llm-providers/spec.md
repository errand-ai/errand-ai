## ADDED Requirements

### Requirement: Local AI detection recognises runtimes that require an API key

A candidate endpoint that rejects an unauthenticated request SHALL be treated as a service that exists and needs credentials, not as an absent one. The scan result SHALL carry these endpoints in a `needs_key` list, alongside `detected` rather than inside it.

Each entry SHALL carry its `base_url` and nothing else. An endpoint answering with an authentication failure returns no body, so nothing further about it is known; reporting a provider type of `unknown` would be a field whose only honest rendering is not to render it, and would invite a caller to display a runtime name that was never established.

`base_url` SHALL be non-null and unique within a scan result. The server constructs it from the host gateway address and a deduplicated candidate port and never takes it from a caller, so a consumer may use it both as identity and as the argument to adoption.

The scan SHALL NOT create a provider for such an endpoint, and SHALL NOT store a placeholder key against it.

#### Scenario: Keyed runtime is reported rather than skipped

- **WHEN** a scan runs and a candidate endpoint rejects the unauthenticated probe as unauthorised
- **THEN** the endpoint appears in `needs_key` with its base URL
- **AND** no provider is created for it

#### Scenario: Entry asserts no runtime name or type

- **WHEN** an endpoint is reported as needing a key
- **THEN** the entry carries only its base URL

#### Scenario: Distinguished from an endpoint with nothing on it

- **WHEN** one candidate endpoint rejects the probe as unauthorised and another does not respond at all
- **THEN** only the first appears in `needs_key`

#### Scenario: Distinguished from a runtime that needs no key

- **WHEN** a scan finds both a runtime that answers the unauthenticated probe and one that rejects it
- **THEN** the first is registered as a provider and appears in `detected`
- **AND** the second appears only in `needs_key`

#### Scenario: Nothing found at all

- **WHEN** a scan runs and no candidate endpoint responds
- **THEN** both `detected` and `needs_key` are empty
- **AND** the operation reports that nothing was found, rather than failing

### Requirement: An endpoint already served by a provider is not reported as needing a key

An endpoint for which a provider is already configured SHALL be excluded from `needs_key`, whatever that provider's source. A caller SHALL NOT have to compare base URLs to determine which reported endpoints it has already adopted.

A detected provider whose stored key has stopped working SHALL NOT reappear in `needs_key`. Supplying a replacement key for a provider that already exists is an edit to that provider; reporting that it is not currently working is the reachability check's responsibility.

#### Scenario: Adopted endpoint is not offered again

- **WHEN** a scan runs after an endpoint has been adopted and its stored key is still accepted
- **THEN** that endpoint appears in `detected` and not in `needs_key`

#### Scenario: An adopted endpoint whose key was rotated is not offered again

- **WHEN** a scan runs and an adopted runtime now rejects its stored key
- **THEN** that endpoint does not appear in `needs_key`
- **AND** its provider is retained

#### Scenario: A manually configured endpoint is not offered

- **WHEN** a candidate endpoint requires a key and a provider of any source is already configured for that base URL
- **THEN** that endpoint does not appear in `needs_key`

### Requirement: A detected runtime can be adopted with a supplied API key

The server SHALL expose `POST /api/llm/providers/adopt-local`, taking a `base_url`, an `api_key`, and an optional `name`. It SHALL probe the endpoint with the supplied key and create a provider only if the key is accepted. The resulting provider SHALL carry `source="detected"`, so that it is labelled, reconciled and timed out as any other detected provider is.

The runtime's name SHALL be taken from the probe response obtained with the supplied key, rather than inferred before a readable response exists. A caller-supplied `name` SHALL take precedence over it.

The operation SHALL report its outcome as a resolved result rather than a failure, as the existing reachability check does: the request was well formed and the probe ran, so what the probe found is a finding and not an error. The response SHALL be HTTP 200 carrying `adopted: true` with the created provider, or `adopted: false` with a machine-readable `reason` and a human-readable `message`. The discriminator SHALL be whether a provider was created, because adoption can fail for reasons other than the key.

`reason` SHALL be one of `key_rejected`, `unreachable`, or `name_conflict`. A caller SHALL be able to distinguish these without matching on `message`, whose wording is not part of this contract. Malformed input SHALL still be rejected with 422, and transport or server faults SHALL still fail.

A `name_conflict` refusal SHALL additionally carry `conflicting_name`: the name the probe identified, which is already held. That name is derived server-side after the key is accepted, so a caller has never seen it and could not otherwise report it without parsing `message`. Without it the user is asked to choose a different name while being told nothing about the one to avoid.

#### Scenario: Adoption with a working key

- **WHEN** a caller adopts a detected endpoint with an API key the runtime accepts
- **THEN** the response reports `adopted: true` with the created provider
- **AND** the provider carries `source="detected"` and the supplied key
- **AND** its name comes from what the probe response identified

#### Scenario: Adoption with a key the runtime rejects

- **WHEN** a caller adopts a detected endpoint with a key the runtime rejects
- **THEN** the response reports `adopted: false` with reason `key_rejected`
- **AND** no provider is created

#### Scenario: Adoption of an endpoint that is not responding

- **WHEN** a caller adopts an endpoint that does not respond
- **THEN** the response reports `adopted: false` with reason `unreachable`
- **AND** no provider is created

#### Scenario: The key works but the name is taken

- **WHEN** a key is accepted but the name identified from the response is already held by another provider
- **THEN** the response reports `adopted: false` with reason `name_conflict`
- **AND** the response carries the identified name that is already held
- **AND** the outcome is distinguishable from a rejected key, because the key was not the problem

#### Scenario: A caller-supplied name resolves a conflict

- **WHEN** a caller adopts an endpoint supplying a name that is not already held
- **THEN** the provider is created with that name

#### Scenario: Adoption reconciles nothing

- **WHEN** an endpoint is adopted
- **THEN** no scan is performed as part of adoption
- **AND** no existing provider is removed

### Requirement: Reconciliation probes an adopted provider with its own key

Before probing a candidate endpoint, the scan SHALL check for an existing detected provider recorded at that endpoint and, where one exists, probe using that provider's stored key rather than the keyless sentinel. A stored key SHALL only ever be sent to the endpoint recorded against the provider that holds it.

A detected provider whose endpoint still responds SHALL be retained, including when its stored key is no longer accepted — a key that has been rotated or revoked is not evidence that the runtime has gone. Reporting such a provider as unusable is the reachability check's responsibility, not the scan's.

#### Scenario: Adopted runtime survives a re-scan

- **WHEN** a scan runs and an adopted keyed runtime still accepts its stored key
- **THEN** its provider is retained and updated

#### Scenario: Rotated key does not delete the provider

- **WHEN** a scan runs and an adopted runtime rejects the stored key
- **THEN** its provider is retained
- **AND** the reachability check reports it as unreachable

#### Scenario: Departed keyed runtime is reconciled away

- **WHEN** a scan runs and an adopted keyed runtime no longer responds at all
- **THEN** its provider is removed

#### Scenario: A stored key is not sent to other endpoints

- **WHEN** a scan probes candidate endpoints and a detected provider exists for one of them
- **THEN** that provider's key is sent only to its own endpoint
- **AND** every other candidate is probed with the keyless sentinel

### Requirement: An unreadable response does not yield a runtime name

Where a probe response cannot be read, the endpoint SHALL be named after itself rather than after the runtime that nominally claims its port. Falling back to a candidate's name is permitted only when a response was read and carried no identifying marker.

#### Scenario: Unreadable response on a port claimed by one runtime

- **WHEN** an endpoint rejects the probe and its port is the default of exactly one known runtime
- **THEN** the endpoint is not named after that runtime

#### Scenario: Readable response with no marker

- **WHEN** an endpoint answers with a model listing carrying no identifying marker and its port is the default of exactly one known runtime
- **THEN** that runtime's name is used
