## ADDED Requirements

### Requirement: Memory settings card

The settings UI SHALL present a Memory card summarising the state of the memory service. The card SHALL show health, the memory service version, stored-item counts, when memory was last written, a growth indicator over time, any failed operations, and token usage over a recent period. All data SHALL come from the errand server; the card SHALL NOT call the memory service directly.

#### Scenario: Healthy memory service

- **WHEN** the card is opened and the memory service is configured and healthy
- **THEN** it shows a healthy indicator, the version, the bank in use, counts, and the time of the last write

#### Scenario: No direct upstream call

- **WHEN** the card loads
- **THEN** every request it issues targets the errand server

#### Scenario: Growth over time

- **WHEN** statistics are available
- **THEN** the card renders a growth indicator derived from the memory time series

### Requirement: Card distinguishes not-configured from unreachable

The card SHALL render three distinct states: memory not configured, memory configured but unreachable, and memory healthy. The not-configured state SHALL read as an available feature that is switched off, not as an error.

#### Scenario: Not configured

- **WHEN** no memory service is configured
- **THEN** the card explains that memory is not enabled
- **AND** does not display an error state

#### Scenario: Configured but unreachable

- **WHEN** a memory service is configured and cannot be reached
- **THEN** the card shows an unreachable state distinct from the not-configured state

### Requirement: Deployment facts are read-only

The card SHALL display the memory service URL state and the bearer as read-only. It SHALL NOT offer editing of the URL or token, and SHALL NOT render the token value.

#### Scenario: Token never rendered

- **WHEN** the card is displayed in any state
- **THEN** no bearer token value appears in the rendered output

#### Scenario: URL not editable from the card

- **WHEN** the card is displayed
- **THEN** no control is offered to change the memory service URL

### Requirement: LLM reachability is a user-triggered control

The card SHALL offer an explicit control to check that the memory service's own LLM is reachable, and SHALL report the outcome inline. The check SHALL NOT run automatically on card load or on any poll.

#### Scenario: Check invoked by the user

- **WHEN** the user activates the check control
- **THEN** the check runs once and its outcome is displayed

#### Scenario: Check unavailable

- **WHEN** the memory service reports the check is disabled
- **THEN** the control is shown as unavailable with an explanation, rather than reporting a failure

### Requirement: Failed operations are surfaced with cause

When the memory service reports failed operations, the card SHALL show how many failed and make each failure's error message and retry state available, so that a user can distinguish a transient retry from a permanent failure.

#### Scenario: Failures shown with cause

- **WHEN** the bank has failed operations
- **THEN** the card shows the count and exposes the error message and retry state for each

#### Scenario: No failures

- **WHEN** the bank has no failed operations
- **THEN** the card shows no failure state

### Requirement: Memory taxonomy is presented in errand's vocabulary

The card SHALL NOT display the memory service's internal fact-type identifiers. Stored-item categories SHALL be rendered with errand's own user-facing labels.

#### Scenario: Internal identifiers not shown

- **WHEN** the card renders category counts
- **THEN** the raw upstream fact-type identifiers do not appear in the rendered output

### Requirement: Panels degrade on reported capability

The card SHALL use the memory service's reported feature flags to decide which panels to render, and SHALL omit a panel whose backing feature is unavailable rather than rendering an error.

#### Scenario: Token usage hidden when tracing unavailable

- **WHEN** the memory service reports that LLM tracing is unavailable
- **THEN** the token usage panel is not rendered
- **AND** no error is shown in its place

#### Scenario: Panels shown when features available

- **WHEN** the memory service reports the corresponding features as available
- **THEN** the matching panels render
