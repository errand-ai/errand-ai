## ADDED Requirements

### Requirement: execute_command output size cap
The `execute_command` tool SHALL enforce a maximum output size calculated as `MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25` characters. When command output exceeds this limit, the tool SHALL truncate the output and append a message explaining the truncation and directing the agent to use file-path-based tools for binary files. The cap SHALL scale dynamically with the configured `MAX_CONTEXT_TOKENS` value.

#### Scenario: Command output within cap
- **WHEN** the agent runs `execute_command("ls -la")` and the output is 500 characters
- **THEN** the full output is returned unchanged

#### Scenario: Command output exceeds cap
- **WHEN** the agent runs `execute_command("base64 /tmp/large-image.png")` and the output is 500,000 characters with a cap of 112,500 characters
- **THEN** the output is truncated to the cap limit and a message is appended explaining the truncation and directing the agent to use file-path-based tools

#### Scenario: Cap scales with model context
- **WHEN** `MAX_CONTEXT_TOKENS` is set to 900,000 (1M context model)
- **THEN** the output cap is approximately 675,000 characters

### Requirement: read_file binary file guidance
When `read_file` encounters a binary file (UTF-8 decode error), it SHALL return an error message that identifies the file as binary and directs the agent to use file-path-based tools for uploading or processing, and `execute_command` with metadata tools (e.g., `file`, `ls -la`) for inspection. The error message SHALL explicitly warn against reading binary contents into the conversation.

#### Scenario: Binary file detected
- **WHEN** the agent calls `read_file` on a PNG image file
- **THEN** the tool returns an error message identifying it as a binary file with guidance to use file-path-based upload tools

#### Scenario: Text file with encoding issues
- **WHEN** the agent calls `read_file` on a file with mixed encoding that cannot be decoded as UTF-8
- **THEN** the same binary file guidance is returned
