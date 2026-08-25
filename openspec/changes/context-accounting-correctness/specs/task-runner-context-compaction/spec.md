## MODIFIED Requirements

### Requirement: Context compaction via LLM summarization

The task runner SHALL compact conversation history when the estimated context size exceeds `MAX_CONTEXT_TOKENS`, replacing the oldest messages with an LLM-generated summary and retaining approximately `KEEP_RECENT_TOKENS` of recent messages.

The size used for the trigger decision SHALL account for the whole prompt, not only the message list. The prompt carries the agent instructions and the JSON schema of every registered tool in addition to the messages, and those are absent from a serialisation of the message list alone.

The runner SHALL derive the trigger size from the most recent measured `input_tokens` reported by the provider, adding the estimated size of messages appended since that measurement. When no measurement is available — the first turn of a task, or a provider reporting no usage — the runner SHALL fall back to serialising the message list and adding a conservative fixed overhead.

A usage block reporting all zeros SHALL be treated as no measurement rather than as a measurement of zero, so the fallback applies rather than a zero baseline.

Compaction SHALL fall back to `_trim_context_window` if the summarization call fails.

#### Scenario: Trigger uses the measured prompt size

- **WHEN** the previous turn reported `input_tokens` of 140,000 and 2,000 tokens of messages have been appended since
- **THEN** the trigger decision is made against approximately 142,000, not against a serialisation of the message list alone

#### Scenario: First turn falls back to estimate plus overhead

- **WHEN** compaction is evaluated before any turn has reported usage
- **THEN** the trigger size is the serialised message size plus the fixed overhead
- **THEN** compaction does not baseline off zero

#### Scenario: Zero usage is not a measurement

- **WHEN** a turn reports a usage block whose values are all zero
- **THEN** that turn does not become the baseline for subsequent trigger decisions
- **THEN** the fallback estimate is used instead

#### Scenario: Below the ceiling, no compaction

- **WHEN** the derived size is below `MAX_CONTEXT_TOKENS`
- **THEN** the message list is returned unchanged

#### Scenario: Summarization failure falls back to trimming

- **WHEN** compaction is triggered and the summarization call fails
- **THEN** `_trim_context_window` is applied instead
- **THEN** the failure is recorded so that backoff and diagnostics behave as already specified
