## ADDED Requirements

### Requirement: Screenshot retention filter for agent context

The task-runner SHALL register a `call_model_input_filter` with the `RunConfig` passed to `Runner.run_streamed()`. The filter SHALL be invoked before every LLM call during the agent run. The filter SHALL scan the conversation history for items containing base64-encoded image data (data URIs matching `data:image/`). The filter SHALL retain the most recent N image items (default: 2) and replace older image content with the text placeholder `[screenshot removed]`. Non-image items SHALL pass through unmodified. The maximum retained screenshot count SHALL be configurable via the `MAX_RETAINED_SCREENSHOTS` environment variable. The filter SHALL log how many screenshots were removed and the approximate size of removed base64 data.

#### Scenario: Old screenshots stripped from context

- **WHEN** the agent has taken 6 screenshots across 6 turns and the LLM is called for turn 7
- **THEN** the filter retains only the 2 most recent screenshots and replaces the 4 oldest with `[screenshot removed]`

#### Scenario: Few screenshots pass through unmodified

- **WHEN** the agent has taken 2 screenshots (at the retention limit)
- **THEN** both screenshots are retained in full

#### Scenario: Non-image tool results unaffected

- **WHEN** the conversation history contains text-only tool results and no screenshots
- **THEN** the filter passes all items through without modification

#### Scenario: Custom retention limit via environment variable

- **WHEN** `MAX_RETAINED_SCREENSHOTS` is set to `3`
- **THEN** the filter retains only the 3 most recent screenshots

### Requirement: Context window trimming

The task-runner SHALL trim the conversation history when estimated token count exceeds `MAX_CONTEXT_TOKENS` (default: 150000). The trimmer SHALL keep the first message (initial user prompt) and drop the oldest messages from the remainder until the estimated token count is under the limit. Token estimation SHALL use a conservative ratio of 3 characters per token to account for base64 image data which tokenizes less efficiently than English text. The `MAX_CONTEXT_TOKENS` limit SHALL be configurable via environment variable. The trimmer SHALL log the message count and estimated token count before and after trimming.

#### Scenario: Context under limit passes through

- **WHEN** the conversation history is estimated at 100,000 tokens
- **THEN** all messages pass through unmodified

#### Scenario: Context trimmed when over limit

- **WHEN** the conversation history is estimated at 200,000 tokens
- **THEN** the oldest messages (after the first) are dropped until the estimate is under 150,000 tokens

#### Scenario: First message always preserved

- **WHEN** context trimming occurs
- **THEN** the first message (initial user prompt) is always retained regardless of its size

### Requirement: RunConfig integration

The task-runner's `main()` function SHALL create a `RunConfig` with the `call_model_input_filter` set to a filter that chains screenshot stripping followed by context window trimming. The `RunConfig` SHALL be passed to `Runner.run_streamed()` alongside the existing `hooks` parameter.

#### Scenario: Filter active during agent execution

- **WHEN** the task-runner runs an agent with the RunConfig
- **THEN** both the screenshot retention filter and context window trimmer are called before each LLM invocation
