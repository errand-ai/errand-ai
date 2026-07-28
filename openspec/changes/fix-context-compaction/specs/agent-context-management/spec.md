## MODIFIED Requirements

### Requirement: Context window trimming

The task-runner SHALL trim the conversation history when estimated token count exceeds `MAX_CONTEXT_TOKENS` (default: 150000). The trimmer SHALL keep the first message (initial user prompt) and drop the oldest messages from the remainder until the estimated token count is **at or below a target level set materially below `MAX_CONTEXT_TOKENS`**, so that trimming leaves headroom for subsequent turns rather than stopping at the threshold. Token estimation SHALL use a conservative ratio of 3 characters per token to account for base64 image data which tokenizes less efficiently than English text. The `MAX_CONTEXT_TOKENS` limit SHALL be configurable via environment variable. The trimmer SHALL log the message count and estimated token count before and after trimming.

Stopping at the threshold leaves zero headroom, so the next tool result re-crosses it immediately and the trimmer — or a failing compaction ahead of it — runs again on the following turn. Observed in production as a re-trigger cadence tightening to roughly one attempt every twelve seconds.

#### Scenario: Context under limit passes through

- **WHEN** the conversation history is estimated at 100,000 tokens
- **THEN** all messages pass through unmodified

#### Scenario: Context trimmed below the limit, not to it

- **WHEN** the conversation history is estimated at 200,000 tokens
- **THEN** the oldest messages (after the first) are dropped until the estimate is at or below the target level
- **AND** the resulting estimate is materially below 150,000 tokens rather than just under it

#### Scenario: Trimming leaves room for subsequent turns

- **WHEN** trimming completes and a subsequent turn adds a tool result of typical size
- **THEN** the conversation does not immediately re-cross `MAX_CONTEXT_TOKENS`

#### Scenario: First message always preserved

- **WHEN** context trimming occurs
- **THEN** the first message (initial user prompt) is always retained regardless of its size
