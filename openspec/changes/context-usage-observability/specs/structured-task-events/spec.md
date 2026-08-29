## ADDED Requirements

### Requirement: Compaction failure is visible in the live view

A failed compaction SHALL emit a dedicated event type that reaches the live task view, carrying the failure reason and the consecutive-failure count. This event SHALL be small: it SHALL NOT carry the context contributor detail.

This event SHALL be additional to, not a replacement for, the `context_snapshot` emitted with `reason: compaction_failed`. That snapshot SHALL remain in the excluded set. The exclusion exists because snapshot payloads are large and would displace real entries in the bounded replay buffer, and that reasoning is unchanged by the need to surface failures.

The exclusion filter SHALL remain a test of event type alone. It SHALL NOT branch on the contents of `data`, so that the decision to exclude stays independent of payload shape.

#### Scenario: Compaction failure reaches the live view

- **WHEN** a compaction attempt fails and the runner falls back to trimming
- **THEN** a compaction-failure event is published to the task's live channel
- **THEN** the event carries the reason and the consecutive-failure count

#### Scenario: The snapshot stays excluded

- **WHEN** a compaction attempt fails
- **THEN** the accompanying `context_snapshot` is not published and is not written to the replay buffer
- **THEN** it remains present in the task runner's container log

#### Scenario: Exclusion is decided by type alone

- **WHEN** the live-path filter evaluates any event
- **THEN** the decision uses the event type only
- **THEN** the payload is not inspected to decide exclusion

#### Scenario: Repeated failures are distinguishable

- **WHEN** compaction fails three times consecutively on one task
- **THEN** three events are emitted, each carrying an increasing consecutive-failure count
