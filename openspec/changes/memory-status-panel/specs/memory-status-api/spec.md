## ADDED Requirements

### Requirement: Memory status proxy

The server SHALL expose read-only endpoints under `/api/memory/` that retrieve memory-service data on behalf of the caller, using the server-held Hindsight URL and bearer token. The set of upstream routes reachable through the proxy SHALL be enumerated in code; the proxy SHALL NOT accept an arbitrary upstream path from the caller.

#### Scenario: Proxy reaches an allowed upstream route

- **WHEN** an authorised caller requests memory status through the proxy and Hindsight is configured and reachable
- **THEN** the response carries the upstream data for that route

#### Scenario: Arbitrary upstream paths are refused

- **WHEN** a caller supplies an upstream path that is not in the enumerated set
- **THEN** the request is rejected
- **AND** no request is made to the memory service

#### Scenario: Bank is a parameter

- **WHEN** any bank-scoped proxy route is called
- **THEN** the bank identifier is taken as a parameter rather than hard-coded, defaulting to the configured bank when omitted

### Requirement: Proxy never discloses memory-service credentials or location

No proxy response SHALL contain the Hindsight base URL, the Hindsight bearer token, or any upstream error body that embeds either. Upstream failures SHALL be reported as a status and a sanitised message.

#### Scenario: Token absent from every response

- **WHEN** any `/api/memory/` endpoint returns, on success or failure
- **THEN** the response body contains neither the configured bearer token nor the Hindsight base URL

#### Scenario: Upstream error is sanitised

- **WHEN** the memory service returns an error whose body includes its own URL or authorisation details
- **THEN** the proxy returns a sanitised message that omits them

### Requirement: Proxy reports configuration state rather than failing

When no Hindsight URL is configured, the proxy SHALL report that memory is not configured, distinctly from reporting that a configured memory service is unreachable. Neither case SHALL be surfaced as a server error.

#### Scenario: Memory not configured

- **WHEN** no Hindsight URL is configured and a status endpoint is called
- **THEN** the response indicates memory is not configured
- **AND** the response is not a server error

#### Scenario: Memory configured but unreachable

- **WHEN** a Hindsight URL is configured and the service does not respond
- **THEN** the response indicates the service is unreachable, distinct from not configured

### Requirement: Health, statistics and diagnostics are exposed

The proxy SHALL expose: liveness and readiness; the memory service version and its feature flags; bank statistics including counts, last write time and last consolidation time; a memory-growth time series; failed operations with their task type, error message, retry count and next retry time; and token usage over a period.

#### Scenario: Status aggregates liveness and version

- **WHEN** the status endpoint is called against a healthy service
- **THEN** the response carries liveness, the memory service version, and the upstream feature flags

#### Scenario: Failed operations expose their retry state

- **WHEN** failed operations are requested and the bank has failures
- **THEN** each entry carries at least the task type, the error message, the retry count and the next retry time

#### Scenario: Token usage returned for a period

- **WHEN** token usage is requested for a period
- **THEN** the response carries input, output and cached token counts bucketed over that period

### Requirement: LLM reachability check is an explicit action

The proxy SHALL expose the memory service's bank LLM health check as an explicitly invoked operation, never as part of an automatically polled status response, because it performs a real LLM request. When the upstream check is disabled, the proxy SHALL report it as unavailable rather than as a failure.

#### Scenario: Check runs only when invoked

- **WHEN** the status endpoint is polled
- **THEN** no LLM health check is performed upstream

#### Scenario: Check disabled upstream

- **WHEN** the LLM check is invoked and the memory service reports the check is disabled
- **THEN** the proxy reports the check as unavailable
- **AND** does not report it as a failed check

### Requirement: Polling contract reflects upstream cost

The status endpoint intended for repeated polling SHALL call only the upstream liveness route, which performs no database access. Statistics, time series, failed operations and token usage SHALL be served only on explicit request, not from the polled path.

#### Scenario: Polled status does no database work upstream

- **WHEN** the pollable status endpoint is called
- **THEN** only the upstream liveness route is called
- **AND** no statistics or readiness route is called

#### Scenario: Statistics fetched on request

- **WHEN** statistics are requested explicitly
- **THEN** the upstream statistics route is called
