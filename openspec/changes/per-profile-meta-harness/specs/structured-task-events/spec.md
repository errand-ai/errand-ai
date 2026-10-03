## ADDED Requirements

### Requirement: Compatible external harness event normalization
Adapters SHALL translate vendor events into the existing stderr `{type,data}` and worker Valkey envelope without changing legacy required fields, end sentinel, preview limit or diagnostic exclusions. Additive metadata SHALL include attempt/sequence/native call identity and harness provenance. Unknown events SHALL become bounded redacted diagnostics and SHALL NOT imply terminal success. Only supported reasoning summaries SHALL be exposed; hidden chain-of-thought SHALL NOT be synthesized or retained.

#### Scenario: Existing frontend consumes an external run
- **WHEN** a qualified external adapter emits mapped start/tool/message/end events
- **THEN** legacy consumers retain their existing rendering and receive the unchanged task_log_end sentinel

#### Scenario: Concurrent native tool calls share a tool name
- **WHEN** two native calls finish out of order
- **THEN** normalized call ids pair results with the correct invocation rather than by tool name alone

#### Scenario: Unknown or malformed vendor event
- **WHEN** an adapter observes an unrecognized variant or truncated JSON
- **THEN** it emits bounded redacted diagnostics or protocol_error as appropriate and does not manufacture a successful result

#### Scenario: Backpressure and excluded diagnostics
- **WHEN** event volume exceeds buffers or context_snapshot is emitted
- **THEN** optional text may be coalesced, terminal errors/outcomes remain reliable, and excluded diagnostics reach neither live publish nor replay buffer

### Requirement: Disclose harness telemetry gaps
Normalized usage/status events SHALL distinguish reported, estimated and unavailable fields and SHALL NOT fabricate SDK-specific turn/context/stall instrumentation for external loops. Metrics/logging SHALL redact secrets and record bounded harness/version/runtime labels with authorized task/attempt trace correlation.

#### Scenario: External loop hides compaction or per-turn tokens
- **WHEN** a harness exposes only final usage or no context counters
- **THEN** the task UI/API discloses unavailable telemetry without fabricated zeroes or llm_turn pairing
