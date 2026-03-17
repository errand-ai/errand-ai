## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: RunConfig integration

The task-runner's `main()` function SHALL create a `RunConfig` with the `call_model_input_filter` set to a filter that chains malformed tool call sanitization, then screenshot stripping, then context window trimming. The `RunConfig` SHALL be passed to `Runner.run_streamed()` alongside the existing `hooks` parameter.

#### Scenario: Filter active during agent execution

- **WHEN** the task-runner runs an agent with the RunConfig
- **THEN** malformed tool call sanitization, screenshot retention filter, and context window trimmer are all called before each LLM invocation
