## Purpose

Context management filters for the task-runner agent: malformed tool call sanitization, screenshot retention, and context window trimming.

## Requirements

### Requirement: Malformed tool call sanitization

The `filter_model_input` function SHALL scan assistant messages in the conversation history for tool calls with malformed JSON arguments before performing screenshot stripping and context trimming. For each tool call, the filter SHALL attempt `json.loads()` on the `arguments` string. If parsing fails, the filter SHALL attempt to repair the JSON by closing unclosed string literals and appending missing closing brackets and braces based on an open-delimiter stack. If repair produces valid JSON, the filter SHALL replace the original arguments with the repaired JSON string. If repair fails, the filter SHALL replace the arguments with `{"error": "malformed_arguments", "original_fragment": "<first 200 chars of original>"}`. The filter SHALL log each sanitization at WARNING level, including the tool name and whether repair succeeded or a placeholder was used.

#### Scenario: Truncated JSON arguments repaired

- **WHEN** the conversation history contains a tool call with arguments `{"path": "/file.md", "content": "hello` (missing closing quote and braces)
- **THEN** the filter repairs the arguments to valid JSON by closing the string and braces, and the repaired arguments pass `json.loads()` successfully

#### Scenario: Completely invalid JSON replaced with placeholder

- **WHEN** the conversation history contains a tool call with arguments that cannot be repaired to valid JSON (e.g. binary garbage)
- **THEN** the filter replaces the arguments with `{"error": "malformed_arguments", "original_fragment": "..."}` containing the first 200 characters of the original

#### Scenario: Valid tool call arguments pass through unchanged

- **WHEN** the conversation history contains tool calls with valid JSON arguments
- **THEN** the filter passes all arguments through without modification

#### Scenario: Sanitization runs before screenshot stripping

- **WHEN** the `filter_model_input` function processes a conversation history with both malformed tool calls and old screenshots
- **THEN** tool call sanitization runs first, followed by screenshot stripping, then context trimming

### Requirement: JSON repair for truncated strings

The JSON repair function SHALL handle truncation — the most common malformation from LLM output. The repair SHALL: (1) detect unclosed string literals by tracking quote parity and append a closing `"` if needed, (2) track a stack of open delimiters (`{`, `[`) and append the corresponding closing delimiters in reverse order, (3) validate the repaired string with `json.loads()`. The repair function SHALL return the repaired string on success or `None` on failure. The repair function SHALL NOT use external dependencies.

#### Scenario: Missing closing brace repaired

- **WHEN** the input is `{"key": "value"` (missing `}`)
- **THEN** the repair function returns `{"key": "value"}` which passes `json.loads()`

#### Scenario: Missing closing quote and brace repaired

- **WHEN** the input is `{"path": "/file.md", "content": "some text`
- **THEN** the repair function closes the string and brace, returning valid JSON

#### Scenario: Nested structure repaired

- **WHEN** the input is `{"data": [{"a": 1}, {"b": 2`
- **THEN** the repair function closes the inner brace, the array, and the outer brace

#### Scenario: Irreparable input returns None

- **WHEN** the input is not recognizable as truncated JSON (e.g. empty string, random text)
- **THEN** the repair function returns `None`

### Requirement: Screenshot retention filter for agent context

The task-runner SHALL register a `call_model_input_filter` with the `RunConfig` passed to `Runner.run_streamed()`. The filter SHALL be invoked before every LLM call during the agent run. The filter SHALL scan the conversation history for items containing base64-encoded image data (data URIs matching `data:image/`). The filter SHALL retain the most recent N image items (default: 2) and replace older image content with the text placeholder `[screenshot removed]`. Non-image items SHALL pass through unmodified. The maximum retained screenshot count SHALL be configurable via the `MAX_RETAINED_SCREENSHOTS` environment variable. The filter SHALL log how many screenshots were removed and the approximate size of removed base64 data.

#### Scenario: Old screenshots stripped from context

- **WHEN** the agent has taken 6 screenshots across 6 turns and the LLM is called for turn 7
- **THEN** the filter retains only the 2 most recent screenshots and replaces the 4 oldest with `[screenshot removed]`

#### Scenario: Few screenshots pass through unmodified

- **WHEN** the agent has taken 2 screenshots (at the retention limit)
- **THEN** both screenshots are retained in full

#### Scenario: Non-image tool results unaffected

- **WHEN** the conversation history contains text-only tool results and no screenshots
- **THEN** the filter passes all items through without modification

#### Scenario: Custom retention limit via environment variable

- **WHEN** `MAX_RETAINED_SCREENSHOTS` is set to `3`
- **THEN** the filter retains only the 3 most recent screenshots

### Requirement: Context window trimming

The task-runner SHALL trim the conversation history when estimated token count exceeds `MAX_CONTEXT_TOKENS` (default: 150000). The trimmer SHALL keep the first message (initial user prompt) and drop the oldest messages from the remainder until the estimated token count is under the limit. Token estimation SHALL use a conservative ratio of 3 characters per token to account for base64 image data which tokenizes less efficiently than English text. The `MAX_CONTEXT_TOKENS` limit SHALL be configurable via environment variable. The trimmer SHALL log the message count and estimated token count before and after trimming.

#### Scenario: Context under limit passes through

- **WHEN** the conversation history is estimated at 100,000 tokens
- **THEN** all messages pass through unmodified

#### Scenario: Context trimmed when over limit

- **WHEN** the conversation history is estimated at 200,000 tokens
- **THEN** the oldest messages (after the first) are dropped until the estimate is under 150,000 tokens

#### Scenario: First message always preserved

- **WHEN** context trimming occurs
- **THEN** the first message (initial user prompt) is always retained regardless of its size

### Requirement: RunConfig integration

The task-runner's `main()` function SHALL create a `RunConfig` with the `call_model_input_filter` set to a filter that chains malformed tool call sanitization, then screenshot stripping, then context window trimming. The `RunConfig` SHALL be passed to `Runner.run_streamed()` alongside the existing `hooks` parameter.

#### Scenario: Filter active during agent execution

- **WHEN** the task-runner runs an agent with the RunConfig
- **THEN** malformed tool call sanitization, screenshot retention filter, and context window trimmer are all called before each LLM invocation

### Requirement: Binary file handling directive in system prompt
The system prompt injected by the server SHALL include a directive instructing the agent never to read binary file contents (images, PDFs, archives, etc.) into the conversation. The directive SHALL explain that binary data will exceed the context window and cause task failure, and SHALL direct the agent to use file-path-based tools for uploading/transferring binary files and metadata commands for inspection.

#### Scenario: System prompt includes binary file directive
- **WHEN** the server prepares the system prompt for a task
- **THEN** the system prompt includes a section about binary file handling that warns against reading binary contents and directs the agent to file-path-based alternatives
