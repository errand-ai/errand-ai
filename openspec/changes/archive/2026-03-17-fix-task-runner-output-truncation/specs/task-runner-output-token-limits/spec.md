## ADDED Requirements

### Requirement: Model-aware max output token resolution

The task-runner SHALL resolve the maximum output tokens for the configured model using a pattern-based lookup table. The lookup SHALL match model name substrings in priority order (most specific patterns first). The lookup table SHALL include entries for Claude (opus-4-6: 128000, opus-4-5: 64000, opus-4-1: 32000, opus-4: 32000, sonnet-4: 64000, haiku-4: 64000, claude-3: 4096), OpenAI (gpt-4.1: 32768, gpt-4o: 16384, gpt-5: 100000), and Google (gemini-2.5: 65535, gemini-2: 65535) model families. If no pattern matches, the lookup SHALL return a default of 16384 tokens. The resolved value SHALL be logged at INFO level at startup.

#### Scenario: Claude Sonnet 4.5 model resolves to 64000

- **WHEN** the `OPENAI_MODEL` env var is set to `claude-sonnet-4-5-20250929`
- **THEN** the max output tokens SHALL resolve to 64000

#### Scenario: Bedrock-prefixed model resolves correctly

- **WHEN** the `OPENAI_MODEL` env var is set to `bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0`
- **THEN** the max output tokens SHALL resolve to 64000 (the prefix does not prevent matching)

#### Scenario: Claude Opus 4.6 resolves to 128000

- **WHEN** the `OPENAI_MODEL` env var is set to `claude-opus-4-6`
- **THEN** the max output tokens SHALL resolve to 128000

#### Scenario: Unknown model resolves to default

- **WHEN** the `OPENAI_MODEL` env var is set to `my-custom-model`
- **THEN** the max output tokens SHALL resolve to 16384

#### Scenario: GPT-4.1 resolves to 32768

- **WHEN** the `OPENAI_MODEL` env var is set to `gpt-4.1`
- **THEN** the max output tokens SHALL resolve to 32768

### Requirement: Max output tokens applied to ModelSettings

The task-runner SHALL set the `max_tokens` field on the agent's `ModelSettings` to the resolved max output tokens value. This value SHALL be passed to the OpenAI-compatible API as the `max_tokens` parameter on every LLM call.

#### Scenario: Agent created with max_tokens set

- **WHEN** the model resolves to 64000 max output tokens
- **THEN** the `Agent` is created with `ModelSettings(max_tokens=64000, ...)`

### Requirement: Environment variable override for max output tokens

The task-runner SHALL check for a `MAX_OUTPUT_TOKENS` env var. If set to a valid positive integer, this value SHALL override the pattern-based lookup result. If set to an invalid value (non-integer, zero, or negative), the env var SHALL be ignored and the lookup table result used instead, with a warning logged.

#### Scenario: Env var overrides lookup

- **WHEN** `MAX_OUTPUT_TOKENS` is set to `32000` and the model would resolve to 64000
- **THEN** the max output tokens SHALL be 32000

#### Scenario: Invalid env var ignored

- **WHEN** `MAX_OUTPUT_TOKENS` is set to `abc`
- **THEN** the env var is ignored, a warning is logged, and the lookup table result is used
