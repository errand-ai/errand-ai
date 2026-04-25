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
