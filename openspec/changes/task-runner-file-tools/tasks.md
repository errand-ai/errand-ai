## 1. File Mutation Queue

- [x] 1.1 Implement `FileMutationQueue` class — module-level dict mapping resolved absolute paths to `asyncio.Lock` instances, with `acquire(path)` context manager

## 2. File Tools

- [x] 2.1 Implement `write_file(path, content)` tool — acquires lock, creates parent dirs if needed, writes content, returns byte count confirmation
- [x] 2.2 Implement `edit_file(path, old_text, new_text)` tool — acquires lock, reads file, validates exactly one match of `old_text`, replaces with `new_text`, returns unified diff
- [x] 2.3 Implement `read_file(path, offset, limit)` tool — reads file with optional line pagination, returns content with line numbers prefixed, no lock

## 3. Integration

- [x] 3.1 Register `write_file`, `edit_file`, and `read_file` in the Agent's `tools` list alongside `execute_command`
- [x] 3.2 Add file tool guidance section to the task runner system prompt instructing the agent to prefer file tools over shell commands for file I/O

## 4. Tests

- [x] 4.1 Test `write_file` creates a new file with correct content and returns byte count
- [x] 4.2 Test `write_file` overwrites an existing file
- [x] 4.3 Test `write_file` creates parent directories if they don't exist
- [x] 4.4 Test `edit_file` replaces exact match and returns diff
- [x] 4.5 Test `edit_file` returns error when no match found
- [x] 4.6 Test `edit_file` returns error when multiple matches found
- [x] 4.7 Test `edit_file` returns error when file does not exist
- [x] 4.8 Test `read_file` returns content with line numbers
- [x] 4.9 Test `read_file` pagination with offset and limit
- [x] 4.10 Test `read_file` returns error when file does not exist
- [x] 4.11 Test `FileMutationQueue` serializes concurrent writes to the same path
- [x] 4.12 Test `FileMutationQueue` allows concurrent writes to different paths
