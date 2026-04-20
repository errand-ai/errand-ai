## Why

The task runner's `execute_command` tool runs arbitrary shell commands, including file writes. When the OpenAI Agents SDK issues parallel tool calls, two commands could write to the same file simultaneously, causing corruption or lost writes. Adding explicit `write_file`, `edit_file`, and `read_file` tools with a per-file mutation queue provides safe, concurrent file operations and gives the agent structured file manipulation capabilities that don't require shell command construction.

## What Changes

- Add `write_file` tool — create or overwrite a file with given content, protected by per-file lock
- Add `edit_file` tool — find-and-replace within a file, protected by per-file lock
- Add `read_file` tool — read file content (with optional offset/limit), no lock required
- Add `FileMutationQueue` — a per-file `asyncio.Lock` map that serializes writes to the same path
- Update the task runner system prompt to instruct the agent to prefer file tools over shell commands for file operations
- `execute_command` remains available for shell operations that aren't pure file I/O

## Capabilities

### New Capabilities
- `task-runner-file-tools`: Structured file manipulation tools with concurrent write protection for the task runner

### Modified Capabilities

## Impact

- `task-runner/main.py` — add three new `@function_tool` functions and `FileMutationQueue` class
- Task runner system prompt — add guidance to prefer file tools for file operations
- No new dependencies — uses stdlib `asyncio.Lock` and file I/O
- No database changes
- No API changes
