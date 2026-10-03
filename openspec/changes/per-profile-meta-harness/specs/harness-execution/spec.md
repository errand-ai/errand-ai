## ADDED Requirements

### Requirement: Single-loop lifecycle and authoritative results
Each attempt SHALL run exactly one selected harness loop. Errand SHALL retain scheduling, isolation, permissions and durable finalization ownership. External success SHALL require an existing Errand output object with status completed or needs_input, string result and string-array questions, successful harness terminal outcome and a valid attempt fencing token. External native structured output or the new scoped result MCP bridge SHALL be candidates until validated; raw vendor stdout, early submission or process exit alone SHALL NOT prove success. Duplicate callback/file candidates SHALL be deduplicated and conflicting external candidates SHALL fail. Builtin output extraction, submit_result last-call-wins/question normalization, plain-text fallback and existing nudge behavior SHALL remain unchanged.

#### Scenario: Builtin adapter extraction
- **WHEN** a legacy task runs through the builtin adapter
- **THEN** golden result/event/tool behavior remains compatible with the existing runner

#### Scenario: External harness needs user input
- **WHEN** a qualified external harness succeeds with a valid needs_input result and questions
- **THEN** the worker retains existing input-needed task behavior rather than marking the user task completed

#### Scenario: Submission precedes vendor failure
- **WHEN** a harness submits a candidate result and later exits nonzero
- **THEN** the attempt is failed and no success is finalized

#### Scenario: Malformed output after a service mutation
- **WHEN** a harness has performed a possible external action but returns invalid output
- **THEN** Errand records result_invalid with partial-effect uncertainty and does not rerun the model to repair it

#### Scenario: Two deliveries or stale attempt completion
- **WHEN** callback/file duplicate delivery or a stale worker completion arrives
- **THEN** one fenced finalization wins and stale/conflicting delivery cannot overwrite it

### Requirement: Bounded cancellation and timeout cleanup
The supervisor SHALL enforce end-to-end wall/startup/shutdown limits, revoke/fence task capabilities on cancellation, request native interrupt or signal, then kill/reconcile the complete process/container tree within approved bounded grace. Cleanup SHALL cover every terminal path and worker restart. Partial effects and uncertain cleanup SHALL remain explicit.

#### Scenario: Harness ignores cancellation
- **WHEN** native interrupt does not stop a harness within grace
- **THEN** the supervisor kills its process/container tree, fences late results and reports cleanup status

#### Scenario: Worker crashes during a run
- **WHEN** a worker restarts after losing an attempt lease
- **THEN** orphan execution is reconciled and no duplicate success or unfenced resumed process is accepted

### Requirement: Side-effect-aware retry and explicit resume
Automatic cross-harness fallback SHALL NOT occur. Automatic retries SHALL be restricted to classified transient preparation or proven side-effect-free failures within existing capped task retry limits. Native tool/network activity, broker mutation or incomplete evidence SHALL count as possible effects. Auth, policy, incompatible version and malformed-output errors SHALL be non-retryable. Manual retry SHALL disclose possible effects. Resume SHALL be disabled initially and later require opt-in, qualified native session compatibility, authorization, encrypted retained state and an exclusive lease; implicit last-session resume SHALL NOT occur.

#### Scenario: Transient failure before execution
- **WHEN** preparation fails transiently before any effects are possible
- **THEN** the same selected harness may retry within the shared capped budget and wall timeout

#### Scenario: Incomplete event stream after native shell start
- **WHEN** execution fails after native tool activity or with uncertain stream completeness
- **THEN** automatic replay/fallback is suppressed unless an approved idempotent contract proves safety

#### Scenario: Cross-profile or incompatible resume
- **WHEN** resume references another principal/profile or incompatible version/policy/catalog
- **THEN** it fails authorization/compatibility validation without loading that session

### Requirement: Honest normalized usage and error taxonomy
Terminal records SHALL retain provenance, exit status and normalized error classes including auth, capability_unavailable, permission_denied, approval_required, transient_provider, quota_exceeded, timeout, cancelled, result_invalid, protocol_error and runtime_failure. Usage SHALL identify scope/source/completeness and use null for unavailable token/cost values. Resumed cumulative counters SHALL NOT be double-counted. Hard cost caps SHALL be advertised only where enforcement is qualified.

#### Scenario: Harness provides no per-turn cost
- **WHEN** only session totals or no cost are available
- **THEN** Errand discloses the scope/gap without synthesizing turn usage or reporting missing cost as zero

#### Scenario: Resumed totals or crash counters reset
- **WHEN** a vendor reports cumulative resumed totals or invalid/zeroed crash totals
- **THEN** accounting deduplicates scoped counters where proven and marks unrecoverable amounts unknown
