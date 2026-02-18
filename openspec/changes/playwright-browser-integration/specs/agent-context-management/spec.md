## ADDED Requirements

### Requirement: Screenshot retention filter for agent context

The task-runner SHALL register a `call_model_input_filter` with the `RunConfig` passed to `Runner.run_streamed()`. The filter SHALL be invoked before every LLM call during the agent run. The filter SHALL scan the conversation history for items containing base64-encoded image data (data URIs matching `data:image/`). The filter SHALL retain the most recent N image items (default: 5) and replace older image content with the text placeholder `[screenshot removed]`. Non-image items SHALL pass through unmodified. The maximum retained screenshot count SHALL be configurable via the `MAX_RETAINED_SCREENSHOTS` environment variable.

#### Scenario: Old screenshots stripped from context

- **WHEN** the agent has taken 10 screenshots across 10 turns and the LLM is called for turn 11
- **THEN** the filter retains only the 5 most recent screenshots and replaces the 5 oldest with `[screenshot removed]`

#### Scenario: Few screenshots pass through unmodified

- **WHEN** the agent has taken 3 screenshots (below the retention limit of 5)
- **THEN** all 3 screenshots are retained in full

#### Scenario: Non-image tool results unaffected

- **WHEN** the conversation history contains text-only tool results and no screenshots
- **THEN** the filter passes all items through without modification

#### Scenario: Custom retention limit via environment variable

- **WHEN** `MAX_RETAINED_SCREENSHOTS` is set to `3`
- **THEN** the filter retains only the 3 most recent screenshots

### Requirement: RunConfig integration

The task-runner's `main()` function SHALL create a `RunConfig` with the `call_model_input_filter` set to the screenshot retention filter. The `RunConfig` SHALL be passed to `Runner.run_streamed()` alongside the existing `hooks` parameter.

#### Scenario: Filter active during agent execution

- **WHEN** the task-runner runs an agent with the RunConfig
- **THEN** the screenshot retention filter is called before each LLM invocation
