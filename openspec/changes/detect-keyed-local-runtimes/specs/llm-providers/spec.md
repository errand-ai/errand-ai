## ADDED Requirements

### Requirement: Local AI detection recognises runtimes that require an API key

A candidate endpoint that rejects an unauthenticated request SHALL be treated as a service that exists and needs credentials, not as an absent one. When a candidate endpoint answers with an authentication or authorisation failure, the scan SHALL report it as a local AI runtime requiring an API key, distinct both from the runtimes it registered and from finding nothing.

The scan SHALL NOT create a provider for such an endpoint, because it holds no key that the endpoint accepts. It SHALL NOT store a placeholder key against it.

#### Scenario: Keyed runtime is reported rather than skipped

- **WHEN** a scan runs and a candidate endpoint rejects the unauthenticated probe as unauthorised
- **THEN** the scan reports a local AI runtime at that endpoint requiring an API key
- **AND** no provider is created for it

#### Scenario: Distinguished from an endpoint with nothing on it

- **WHEN** one candidate endpoint rejects the probe as unauthorised and another does not respond at all
- **THEN** only the first is reported as requiring an API key

#### Scenario: Distinguished from a runtime that needs no key

- **WHEN** a scan finds both a runtime that answers the unauthenticated probe and one that rejects it
- **THEN** the first is registered as a provider
- **AND** the second is reported separately as requiring an API key

#### Scenario: Nothing found at all

- **WHEN** a scan runs and no candidate endpoint responds
- **THEN** neither registered runtimes nor key-requiring runtimes are reported
- **AND** the operation reports that nothing was found, rather than failing

### Requirement: A detected runtime can be adopted with a supplied API key

The server SHALL expose an operation that creates a provider for a detected endpoint from a caller-supplied API key. The endpoint SHALL be probed with that key, and the provider created only if the key is accepted. The resulting provider SHALL carry `source="detected"`, so that it is labelled, reconciled and timed out as any other detected provider is.

The runtime's name SHALL be taken from the probe response obtained with the supplied key, rather than inferred before a readable response exists.

#### Scenario: Adoption with a working key

- **WHEN** a caller adopts a detected endpoint with an API key the runtime accepts
- **THEN** a provider is created for that endpoint with `source="detected"`
- **AND** the supplied key is stored
- **AND** its name comes from what the probe response identified

#### Scenario: Adoption with a key the runtime rejects

- **WHEN** a caller adopts a detected endpoint with a key the runtime rejects
- **THEN** no provider is created
- **AND** the caller is told the key was not accepted

#### Scenario: Adoption of an endpoint that is not responding

- **WHEN** a caller adopts an endpoint that does not respond
- **THEN** no provider is created
- **AND** the caller is told the endpoint could not be reached

#### Scenario: Adopted provider is not re-reported as needing a key

- **WHEN** a scan runs after an endpoint has been adopted
- **THEN** that endpoint is not reported as requiring an API key

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
