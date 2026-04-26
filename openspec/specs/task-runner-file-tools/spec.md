## ADDED Requirements

### Requirement: Write file tool
The task runner SHALL provide a `write_file` tool that creates or overwrites a file with given content, protected by a per-file mutation lock.

#### Scenario: Write new file
- **WHEN** the agent calls `write_file` with a path that does not exist
- **THEN** the tool SHALL create parent directories if needed
- **THEN** the tool SHALL write the content to the file
- **THEN** the tool SHALL return confirmation with the byte count written

#### Scenario: Overwrite existing file
- **WHEN** the agent calls `write_file` with a path that already exists
- **THEN** the tool SHALL overwrite the file with the new content
- **THEN** the tool SHALL return confirmation with the byte count written

#### Scenario: Concurrent writes to the same file
- **WHEN** two `write_file` calls target the same file path concurrently
- **THEN** the tool SHALL serialize the writes via a per-file lock
- **THEN** each write SHALL complete without corruption

### Requirement: Edit file tool
The task runner SHALL provide an `edit_file` tool that performs exact-match find-and-replace within a file, protected by a per-file mutation lock.

#### Scenario: Successful edit
- **WHEN** the agent calls `edit_file` with `old_text` that matches exactly once in the file
- **THEN** the tool SHALL replace `old_text` with `new_text`
- **THEN** the tool SHALL return a unified diff preview of the change

#### Scenario: No match found
- **WHEN** the agent calls `edit_file` with `old_text` that does not exist in the file
- **THEN** the tool SHALL return an error message indicating no match was found

#### Scenario: Multiple matches found
- **WHEN** the agent calls `edit_file` with `old_text` that matches more than once
- **THEN** the tool SHALL return an error message indicating multiple matches and requesting more context for a unique match

#### Scenario: File does not exist
- **WHEN** the agent calls `edit_file` with a path that does not exist
- **THEN** the tool SHALL return an error message indicating the file was not found

### Requirement: Read file tool
The task runner SHALL provide a `read_file` tool that reads file content with optional line-based pagination.

#### Scenario: Read entire file
- **WHEN** the agent calls `read_file` with a path and no offset or limit
- **THEN** the tool SHALL return the file content with line numbers prefixed

#### Scenario: Read with pagination
- **WHEN** the agent calls `read_file` with `offset` and `limit` parameters
- **THEN** the tool SHALL return lines starting at `offset` (0-based) up to `limit` lines
- **THEN** the tool SHALL include line numbers in the output

#### Scenario: File does not exist
- **WHEN** the agent calls `read_file` with a path that does not exist
- **THEN** the tool SHALL return an error message indicating the file was not found

### Requirement: File mutation queue
The task runner SHALL maintain a per-file lock system that prevents concurrent writes to the same file path.

#### Scenario: Lock acquisition for write operations
- **WHEN** `write_file` or `edit_file` is called
- **THEN** the tool SHALL acquire the lock for the resolved absolute file path before performing the operation
- **THEN** the tool SHALL release the lock after the operation completes

#### Scenario: No lock for read operations
- **WHEN** `read_file` is called
- **THEN** the tool SHALL NOT acquire any lock

#### Scenario: Different files not blocked
- **WHEN** `write_file` is called for `/workspace/a.txt` and `write_file` is called concurrently for `/workspace/b.txt`
- **THEN** both operations SHALL proceed concurrently without blocking each other

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
