## Context

The task runner (`task-runner/main.py`) provides a single `execute_command` tool that runs arbitrary shell commands via `subprocess.run`. The OpenAI Agents SDK can issue parallel tool calls, meaning two `execute_command` calls could write to the same file simultaneously. Adding structured file tools with a per-file lock provides safe concurrent access and cleaner file manipulation semantics.

## Goals / Non-Goals

**Goals:**
- Add `write_file`, `edit_file`, and `read_file` as `@function_tool` functions
- Protect concurrent writes to the same file path via a per-file asyncio lock
- Guide the agent to prefer file tools over shell commands for file I/O
- Keep `execute_command` available for non-file shell operations

**Non-Goals:**
- Locking files accessed via `execute_command` (can't reliably extract file paths from shell commands)
- Directory-level locking or recursive locks
- File watching or change detection
- Replacing `execute_command` entirely

## Decisions

### 1. Per-file `asyncio.Lock` via `FileMutationQueue`

A module-level dictionary mapping file paths (resolved to absolute) to `asyncio.Lock` instances. `write_file` and `edit_file` acquire the lock for their target path before executing. `read_file` does not acquire locks (reads are safe concurrent with other reads; reads concurrent with writes may see partial state, but this is acceptable — the LLM will retry if output looks wrong).

**Rationale:** Matches Pi's approach. `asyncio.Lock` is lightweight and sufficient since all tools execute in the same event loop. No need for file-system-level locking (flock) since there's a single agent process.

**Alternative considered:** `threading.Lock` — rejected because the Agents SDK tool execution is async, not threaded.

### 2. `write_file(path, content)` — create or overwrite

Acquires lock, writes content to path, creates parent directories if needed. Returns confirmation with byte count.

### 3. `edit_file(path, old_text, new_text)` — find and replace

Acquires lock, reads file, finds `old_text` (exact match), replaces with `new_text`. Fails if `old_text` not found or matches multiple times (agent must provide enough context for a unique match). Returns a unified diff preview of the change.

**Rationale:** Exact-match find/replace is the same pattern used by Pi's `edit` tool and Claude Code's `Edit` tool. It's simple, predictable, and the LLM already understands this paradigm.

### 4. `read_file(path, offset, limit)` — read with pagination

No lock. Reads file content, optionally starting at line `offset` and returning `limit` lines. Returns content with line numbers prefixed.

**Rationale:** Large files need pagination to avoid flooding the context window. Line numbers help the agent reference specific locations for subsequent edits.

### 5. Tools are `@function_tool` (not MCP)

Implemented as OpenAI Agents SDK `@function_tool` functions alongside `execute_command`, not as MCP tools.

**Rationale:** These are core task-runner tools, not external services. They need access to the container's filesystem directly. MCP would add unnecessary network overhead and complexity.

### 6. System prompt guidance

Add a section to the task runner system prompt:

```
## File Operations
For reading, writing, and editing files, prefer the dedicated file tools
(read_file, write_file, edit_file) over shell commands. These tools provide
safer concurrent access and structured output. Use execute_command for
non-file operations (installing packages, running tests, git commands, etc.).
```

**Rationale:** The LLM needs explicit guidance to prefer the new tools. Without it, it will default to familiar shell commands like `cat` and `echo >`.

## Risks / Trade-offs

- **LLM adoption** — The agent may still use `execute_command` for file operations despite system prompt guidance. Mitigation: the prompt is explicit; most modern LLMs follow tool preference instructions well.
- **Lock scope** — Only protects file tools, not `execute_command` writes. Mitigation: accepted limitation; the system prompt steers the agent toward file tools. Full protection would require parsing shell commands, which is fragile.
- **Lock accumulation** — The lock dictionary grows with each unique file path. Mitigation: task runner processes are short-lived (one task per container), so memory is bounded.

## Open Questions

- Should `edit_file` support regex patterns in addition to exact match? Starting with exact match only (simpler, less error-prone).
