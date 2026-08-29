## MODIFIED Requirements

### Requirement: Tool result output size cap

Tool results that return bulk text SHALL be bounded by a maximum size calculated as `MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25` characters. The cap SHALL scale dynamically with the configured `MAX_CONTEXT_TOKENS` value.

The cap SHALL apply to both `execute_command` output and `read_file` content. No single tool result may exceed the context ceiling it has to fit inside.

When a result exceeds the limit, the tool SHALL truncate it and append a message stating the original size and the limit, followed by guidance appropriate to that tool:

- `execute_command` SHALL direct the agent to file-path-based tools, since it has no narrower read available.
- `read_file` SHALL direct the agent to its own `offset` and `limit` parameters, since pagination is a remedy it can act on within the same tool.

Truncation SHALL be logged at `WARNING` with the original size, the truncated size, and the limit, so that a task hitting the cap is visible in the container log without reproducing it.

#### Scenario: Command output within cap

- **WHEN** the agent runs `execute_command("ls -la")` and the output is 500 characters
- **THEN** the full output is returned unchanged

#### Scenario: Command output exceeds cap

- **WHEN** the agent runs `execute_command("base64 /tmp/large-image.png")` and the output is 500,000 characters with a cap of 112,500 characters
- **THEN** the output is truncated to the cap limit and a message is appended explaining the truncation and directing the agent to use file-path-based tools

#### Scenario: File content within cap

- **WHEN** the agent calls `read_file` on a 4,000-character file with a cap of 112,500 characters
- **THEN** the full content is returned unchanged, with line numbers prefixed

#### Scenario: File content exceeds cap

- **WHEN** the agent calls `read_file` on a file whose content is 908,499 characters with a cap of 112,500 characters
- **THEN** the content is truncated to the cap limit
- **THEN** the appended message states the original character count and the limit
- **THEN** the appended message directs the agent to re-read using `offset` and `limit`

#### Scenario: Truncation is logged

- **WHEN** any tool result is truncated by the cap
- **THEN** a `WARNING` is logged recording the original size, the truncated size, and the limit

#### Scenario: Cap scales with model context

- **WHEN** `MAX_CONTEXT_TOKENS` is set to 900,000 (1M context model)
- **THEN** the output cap is approximately 675,000 characters
