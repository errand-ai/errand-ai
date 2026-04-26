## Context

The task-runner agent has file tools (`execute_command`, `read_file`, `write_file`, `edit_file`) that operate on the local filesystem. When the agent generates a binary file (e.g., a PNG image) and needs to upload it to an external service (e.g., Google Drive), it tends to read the file contents into the conversation to pass to an upload tool. For binary files, this means base64-encoding via `execute_command("base64 /path/to/file")`, which can produce hundreds of thousands of tokens in a single tool result.

The model's context window (typically 196K-204K tokens for minimax-m2.5, up to 1M for some models) cannot accommodate this. The LLM API returns a 400 error, and the task-runner's error resilience classifies it as non-retryable, causing the task to fail.

The `MAX_CONTEXT_TOKENS` env var is already passed to the task-runner and represents the usable context budget. It defaults to 150,000 but can be set per-model by the server.

## Goals / Non-Goals

**Goals:**
- No single tool result can blow past the model's context window
- The agent receives clear guidance when output is truncated, directing it to file-path-based alternatives
- Binary file reads are caught early with actionable error messages
- The system prompt discourages binary file reading as a general practice

**Non-Goals:**
- Changing the context compaction algorithm (it already works correctly for normal-sized messages)
- Adding image/binary support to the LLM conversation (the agent is text-only)
- Changing how Google Drive upload works (it already accepts file paths)

## Decisions

### D1: Dynamic output cap as a fraction of MAX_CONTEXT_TOKENS

**Decision**: Cap `execute_command` output at `MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 0.25` characters. With `CHARS_PER_TOKEN = 3` and `MAX_CONTEXT_TOKENS = 150,000`, this gives a cap of ~112,500 characters (~37,500 tokens). For a 1M-context model (`MAX_CONTEXT_TOKENS = 900,000`), the cap would be ~675KB — large enough to handle most command outputs.

**Rationale**: 25% of the context budget is generous for a single tool result while leaving room for system prompt (~5-10%), conversation history (~40-50%), and model output (~15-25%). The cap scales automatically with the model's capabilities.

### D2: Truncation message guides the agent

**Decision**: When output is truncated, replace the excess with a message:
```
[OUTPUT TRUNCATED — was N characters, limit is M characters]
This output exceeds the context window budget. For binary files (images, archives, etc.), do not read contents into the conversation. Use file-path-based tools to upload or process them directly (e.g., Google Drive upload_file with the file path).
```

**Rationale**: The agent needs to understand both what happened and what to do instead. Without guidance, it may retry the same approach.

### D3: read_file binary detection with actionable guidance

**Decision**: When `read_file` encounters a UTF-8 decode error on a binary file, return:
```
Error: Binary file detected (not UTF-8 text). Do not attempt to read binary file contents into the conversation — this will exceed the context window. To work with this file, use execute_command for metadata (e.g., file size, type) or use file-path-based upload tools to transfer it directly.
```

**Rationale**: The current error (`'utf-8' codec can't decode byte 0xff`) tells the agent what failed but not what to do. The improved message prevents the agent from falling back to `base64` as a workaround.

### D4: System prompt binary file directive

**Decision**: Add to the system prompt injected by the server:
```
## Binary Files
Never read binary file contents (images, PDFs, archives, etc.) into the conversation.
Binary data will exceed the context window and cause task failure. To upload or transfer
binary files, use file-path-based tools that accept a file path argument (e.g., Google
Drive upload_file). To inspect binary files, use execute_command with tools like `file`,
`ls -la`, or `identify` (for images).
```

**Rationale**: Proactive guidance is more reliable than reactive error handling. The agent should never attempt to read binary data in the first place.

## Risks / Trade-offs

**[Risk] Legitimate large text output truncated** → A 112KB text output cap is generous for most commands. The rare case of legitimately large text output (e.g., `cat` on a large log file) would be truncated. The message guides the agent to use `read_file` with pagination instead, which is the correct approach anyway.

**[Risk] Agent ignores truncation message** → Possible but unlikely — the message is clear and the alternative approach (file-path tools) is simpler. If the agent retries the same approach, it gets the same truncation, not a crash.
