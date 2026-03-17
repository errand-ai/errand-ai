## MODIFIED Requirements

### Requirement: Malformed tool call sanitization in model input filter

The `_sanitize_tool_calls` function SHALL scan input items in Responses API format. It SHALL iterate the input list looking for dict items with `"type": "function_call"` and validate the `"arguments"` field as parseable JSON. When invalid JSON arguments are detected, the function SHALL attempt to repair the JSON using the existing `_repair_truncated_json` helper. If repair succeeds, the repaired arguments SHALL replace the original. If repair fails, the arguments SHALL be replaced with a JSON object containing an error placeholder: `{"error": "malformed_arguments", "original_fragment": "<first 200 chars>"}`. The function SHALL log a warning for each sanitized tool call.

#### Scenario: Valid function_call items pass through unchanged

- **WHEN** the input contains a `{"type": "function_call", "arguments": "{\"path\": \"/file.md\", \"content\": \"hello\"}"}` item
- **THEN** the item is returned unchanged

#### Scenario: Truncated function_call arguments are repaired

- **WHEN** the input contains a `{"type": "function_call", "arguments": "{\"path\": \"/file.md\""}` item (unclosed brace)
- **THEN** the arguments are repaired to `{"path": "/file.md"}` and a warning is logged

#### Scenario: Unrepairable function_call arguments get error placeholder

- **WHEN** the input contains a `{"type": "function_call"}` item with arguments that cannot be repaired to valid JSON
- **THEN** the arguments are replaced with `{"error": "malformed_arguments", "original_fragment": "..."}` and a warning is logged

#### Scenario: Non-function_call items are ignored

- **WHEN** the input contains items with types other than `"function_call"` (e.g. `"message"`, `"function_call_output"`)
- **THEN** those items are not modified by the sanitization

### Requirement: Truncation-aware error message injection

When the sanitization filter detects and repairs a malformed `function_call` item, it SHALL search the remaining input items for a corresponding `function_call_output` item with a matching `call_id`. If found, the filter SHALL replace the output text with a truncation recovery message. The message SHALL state that the tool call arguments were truncated due to output token limits, the tool call failed, and the LLM should retry by splitting large content into multiple smaller tool calls. The original tool output text SHALL be preserved in the replacement message for context.

#### Scenario: Truncation error message injected into matching tool output

- **WHEN** a `function_call` item with `call_id` "abc123" has malformed arguments AND a `function_call_output` item with `call_id` "abc123" exists
- **THEN** the `function_call_output` item's output is replaced with a message containing: the word "truncated", guidance to split into smaller calls, and the original error text

#### Scenario: No matching tool output — sanitization only

- **WHEN** a `function_call` item has malformed arguments but no corresponding `function_call_output` item exists in the input
- **THEN** the arguments are repaired/replaced but no output item is modified

#### Scenario: Multiple truncated tool calls handled independently

- **WHEN** the input contains two `function_call` items with malformed arguments, each with different `call_id` values
- **THEN** each is repaired independently and each matching `function_call_output` receives the truncation error message
