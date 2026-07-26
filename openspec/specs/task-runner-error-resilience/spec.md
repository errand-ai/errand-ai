## Purpose

Error classification, retry logic for transient LLM API failures, and structured error event emission in the task-runner agent loop.
## Requirements
### Requirement: LLM API error classification

The task-runner SHALL classify exceptions from `Runner.run_streamed()` and its streaming iteration into error categories. Transient errors SHALL include `APIConnectionError`, `APITimeoutError`, `RateLimitError`, and HTTP status codes 429, 502, 503, 504. Non-retryable errors SHALL include `BadRequestError` (400), `AuthenticationError` (401), and any error whose message indicates conversation history corruption (e.g. "Unable to convert openai tool calls"). All other errors SHALL be classified as unknown. The classification function SHALL accept an exception and return one of: `"transient"`, `"non_retryable"`, or `"unknown"`.

#### Scenario: Rate limit error classified as transient

- **WHEN** the LLM API returns a `RateLimitError` (HTTP 429)
- **THEN** the error is classified as `"transient"`

#### Scenario: Connection timeout classified as transient

- **WHEN** the LLM API raises an `APITimeoutError`
- **THEN** the error is classified as `"transient"`

#### Scenario: Bad request classified as non-retryable

- **WHEN** the LLM API returns a `BadRequestError` (HTTP 400)
- **THEN** the error is classified as `"non_retryable"`

#### Scenario: LiteLLM tool conversion error classified as non-retryable

- **WHEN** the LLM API returns HTTP 500 with a message containing "Unable to convert openai tool calls"
- **THEN** the error is classified as `"non_retryable"`

#### Scenario: Unexpected error classified as unknown

- **WHEN** the agent loop raises a `KeyError` or other non-API exception
- **THEN** the error is classified as `"unknown"`

### Requirement: In-process retry for transient LLM errors

The task-runner SHALL retry the agent execution loop when a transient error occurs. The retry SHALL use exponential backoff starting at 2 seconds with a maximum of 3 total attempts (1 initial + 2 retries, delays: 2s, 4s). Each retry SHALL restart `Runner.run_streamed()` from the original user prompt (fresh conversation). If all attempts are exhausted, the task-runner SHALL exit with code 1 as today. The retry count and delay SHALL be logged at INFO level for each attempt.

#### Scenario: Transient error retried successfully

- **WHEN** the first agent execution attempt fails with a `RateLimitError` and the second attempt succeeds
- **THEN** the task completes successfully after one retry, with the retry logged

#### Scenario: All retries exhausted

- **WHEN** all 3 retry attempts fail with transient errors
- **THEN** the task-runner emits an error event and exits with code 1

#### Scenario: Non-retryable error not retried

- **WHEN** the agent execution fails with a `BadRequestError`
- **THEN** the task-runner exits immediately with code 1 without retrying

### Requirement: Structured error event emission

The task-runner SHALL emit error events with additional classification fields. The error event format SHALL be `{"type": "error", "data": {"message": "<error text>", "error_type": "<transient|non_retryable|unknown>", "error_class": "<exception class name>"}}`. The `message` field SHALL contain the string representation of the exception. The `error_type` field SHALL contain the classification result. The `error_class` field SHALL contain the exception's class name (e.g. `"RateLimitError"`, `"APIConnectionError"`).

#### Scenario: Error event includes classification

- **WHEN** the agent execution fails with an `APIConnectionError` after all retries
- **THEN** the emitted error event includes `"error_type": "transient"` and `"error_class": "APIConnectionError"`

#### Scenario: Error event backward compatible

- **WHEN** the task-runner emits an error event
- **THEN** the event includes a `message` field containing the error text, preserving the existing format

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

### Requirement: Empty response error event emission

When the agent loop completes without exception but produces empty output, the task-runner SHALL emit a structured error event. The event format SHALL be `{"type": "error", "data": {"message": "LLM returned empty response", "error_type": "empty_response", "error_class": "EmptyResponseError"}}`. This event SHALL be emitted via the existing `emit_event()` mechanism to stderr, consistent with the error event format defined in the structured error event emission requirement.

#### Scenario: Error event emitted for empty response

- **WHEN** the agent loop completes and `result.final_output` is empty
- **THEN** an error event is emitted to stderr with `"type": "error"`, `"error_type": "empty_response"`, and `"error_class": "EmptyResponseError"`

#### Scenario: Error event format matches existing error events

- **WHEN** an empty response error event is emitted
- **THEN** the event JSON contains the same fields as other error events: `message`, `error_type`, and `error_class`

### Requirement: CancelledError handling in task processing
The task manager's `_run_task` coroutine SHALL catch `asyncio.CancelledError` and attempt to schedule the task for retry before re-raising the exception. If `_schedule_retry` itself fails during the CancelledError handler (e.g., because the DB connection is also closing), the exception SHALL be logged and the CancelledError SHALL still be re-raised. The zombie cleanup mechanism serves as the safety net for tasks that cannot be retried during cancellation.

#### Scenario: Task cancelled during container execution
- **WHEN** the `_run_task` coroutine receives a CancelledError after the container has exited but before `_schedule_retry` is called
- **THEN** the task is scheduled for retry with output indicating processing was cancelled, and the CancelledError is re-raised

#### Scenario: Task cancelled and retry also fails
- **WHEN** the `_run_task` coroutine receives a CancelledError and `_schedule_retry` raises an exception (e.g., DB connection closed)
- **THEN** the failure is logged, the CancelledError is re-raised, and the zombie cleanup will recover the task on the next cycle

### Requirement: execute_command detects Google's raw 401 in addition to UNAUTHENTICATED

The task-runner's `execute_command` wrapper in `task-runner/main.py` SHALL trigger the transparent Google Workspace token refresh path on either of:

1. The existing substring `"status": "UNAUTHENTICATED"` anywhere in the combined stdout+stderr output (current behaviour), OR
2. The conjunction of `"code": 401` AND `"Request had invalid authentication credentials"` anywhere in the combined output (Google's raw API 401 shape).

When either condition matches, the wrapper SHALL proceed exactly as the existing path: call `POST ${ERRAND_API_URL}/api/google/refresh-token`, mutate `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` with the new token, emit a `token_refreshed` event to the transcript, and re-run the same command once. The existing one-retry-per-invocation cap, the module-level refresh lock, and the rest of the recovery flow SHALL be unchanged.

The detection SHALL be case-sensitive and SHALL match the substrings as literals, not regular expressions, to mirror the existing implementation style and avoid false positives from arbitrary CLI output.

#### Scenario: gws CLI returns Google's raw 401 and refresh fires

- **WHEN** `execute_command` runs a `gws drive files list` invocation and the combined output contains `"code": 401` and `"Request had invalid authentication credentials"`
- **THEN** the wrapper calls the errand server's `/api/google/refresh-token` endpoint, updates the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable, emits a `token_refreshed` event, and re-runs the same command exactly once

#### Scenario: Legacy UNAUTHENTICATED path unchanged

- **WHEN** a tool emits the substring `"status": "UNAUTHENTICATED"` in its output
- **THEN** the wrapper triggers token refresh as it does today; the new 401-detection clause is not consulted (either condition is sufficient)

#### Scenario: Partial match does not trigger refresh

- **WHEN** the combined output contains `"code": 401` but not the `"Request had invalid authentication credentials"` substring (e.g. an unrelated CLI returning a 401 with a different message)
- **THEN** the wrapper does NOT trigger token refresh; the conjunction is required, not just the code

#### Scenario: Refresh cap still applies under the new detection

- **WHEN** `execute_command` detects Google's raw 401, refreshes the token, re-runs the command, and the rerun also returns a raw 401
- **THEN** the wrapper does NOT refresh a second time within the same invocation; the existing one-retry-per-invocation cap is honoured and the failure is surfaced

### Requirement: Recover XML-shaped tool calls emitted in reasoning_content

The task-runner SHALL wrap `client.chat.completions.create` (where `client` is the `AsyncOpenAI` instance constructed at startup and registered via `set_default_openai_client`) with an interceptor that inspects every chat-completion response before returning it to the agents-SDK. The interceptor SHALL handle both the non-streaming path (a `ChatCompletion` response) and the streaming path (an `AsyncStream[ChatCompletionChunk]` returned when `kwargs.get("stream")` is true — which is the path the openai-agents SDK uses by default).

When the response shape matches:

1. `content` is `""` or `None` (`choices[0].message.content` in the non-streaming case; accumulated `delta.content` across all chunks in the streaming case), AND
2. No `tool_calls` were emitted (`choices[0].message.tool_calls` is `None` or `[]` in the non-streaming case; no chunk had `delta.tool_calls` in the streaming case), AND
3. `reasoning_content` is a non-empty string (`choices[0].message.reasoning_content` in the non-streaming case; accumulated `delta.reasoning_content` across all chunks in the streaming case), AND
4. `reasoning_content` contains at least one `<tool_call>` substring

then the interceptor SHALL parse the Qwen-XML tool-call blocks from `reasoning_content`, construct the recovered tool-call entries, and surface them to the agents-SDK:

- **Non-streaming**: mutate `choices[0].message.tool_calls` to a list of `ChatCompletionMessageToolCall` entries in place.
- **Streaming**: yield one additional synthesised `ChatCompletionChunk` after all inner chunks, carrying `delta.role="assistant"`, `delta.tool_calls=[ChoiceDeltaToolCall(...)]` with the recovered calls, and `finish_reason="tool_calls"`. The agents-SDK stream handler accumulates this exactly as it would a model-emitted tool call.

In both paths, the agents-SDK SHALL then proceed as if the model had emitted a proper tool-calling response.

Responses that fail any of the four conditions SHALL be returned unchanged. The interceptor SHALL NOT touch `usage`, `finish_reason` of original chunks/messages, or any field other than `tool_calls` (non-streaming) and the appended synthetic chunk (streaming).

The interceptor SHALL be active for every chat completion the runner makes — there is no opt-out setting.

#### Scenario: Qwen-XML tool call in reasoning_content is recovered

- **WHEN** the LLM response has `content=""`, `tool_calls=None`, and `reasoning_content` contains `<tool_call><function=execute_command><parameter=command>ls</parameter></function></tool_call>`
- **THEN** the post-processor sets `choices[0].message.tool_calls` to a single `ChatCompletionMessageToolCall` with `function.name="execute_command"` and `function.arguments=json.dumps({"command": "ls"})`, and the agents-SDK invokes the tool normally

#### Scenario: Well-formed tool_calls response is pass-through

- **WHEN** the LLM response has a non-empty `tool_calls` list (model emitted them correctly)
- **THEN** the post-processor returns the response unchanged; `tool_calls` is not touched

#### Scenario: Non-empty content response is pass-through

- **WHEN** the LLM response has non-empty `content` (model emitted a text answer)
- **THEN** the post-processor returns the response unchanged

#### Scenario: Reasoning without tool_call markup is pass-through

- **WHEN** `content` is empty and `tool_calls` is null but `reasoning_content` contains only prose (no `<tool_call>` substring)
- **THEN** the post-processor returns the response unchanged and the agents-SDK proceeds with its existing empty-response handling (nudge or `EmptyResponseError`)

#### Scenario: Multiple XML tool calls in one reasoning block

- **WHEN** `reasoning_content` contains two `<tool_call>...</tool_call>` blocks
- **THEN** the post-processor recovers both; `choices[0].message.tool_calls` is a 2-element list

#### Scenario: Streaming response with XML tool call across chunks is recovered

- **WHEN** the agents-SDK calls `create(stream=True)` and the inner `AsyncStream` delivers chunks whose `delta.content` is empty, `delta.tool_calls` is never set, and `delta.reasoning_content` accumulates Qwen-XML markup for a single `<tool_call>` block split across chunks, with a final chunk carrying `finish_reason="stop"`
- **THEN** the wrapper forwards every original chunk untouched and appends one additional synthesised `ChatCompletionChunk` whose `delta.tool_calls` carries the recovered call and whose `finish_reason="tool_calls"`; the agents-SDK stream handler accumulates the synthetic chunk as the model's tool call and the agent loop proceeds normally

### Requirement: Qwen-XML tool-call parser supports common dialect variants

The parser SHALL recognise the following Qwen-XML variants when extracting a tool call from a `<tool_call>...</tool_call>` block:

**Function name** — first matching form wins:
- `<function=NAME>...</function>` (attribute form)
- `<function_name>NAME</function_name>` (element form)

**Arguments** — first matching form wins:
- `<arguments>{...JSON...}</arguments>` — JSON blob; parsed via `json.loads`. The capture regex SHALL be greedy and anchored to `</arguments>` so nested-object JSON (e.g. `{"server": {"host": "localhost"}, "retries": 3}`) is captured in full rather than truncated at the first inner `}`.
- One or more `<parameter=KEY>VALUE</parameter>` tags — collected into a `{KEY: VALUE}` dict with VALUE kept as a string
- One or more `<parameter><name>KEY</name><value>VALUE</value></parameter>` verbose-form tags — collected into a `{KEY: VALUE}` dict

If a block matches `<tool_call>` boundaries but neither the function-name forms nor any argument form can be extracted, the block SHALL be skipped and a `tool_call_recovery_failed` event SHALL be emitted. The remaining blocks (if any) SHALL still be processed.

Argument values for the key-value forms SHALL be passed through verbatim as strings. JSON-blob arguments SHALL be serialised via `json.dumps` before being placed on `function.arguments` (matching the OpenAI wire format, which expects a JSON-encoded string there).

Each recovered tool call SHALL be assigned a unique `id` of the form `call_recovered_<12-hex-chars>` so the agents-SDK's tool-call matching invariants hold across the turn.

#### Scenario: Attribute-form function with key/value parameters

- **WHEN** the block is `<tool_call><function=ls><parameter=path>/tmp</parameter><parameter=long>true</parameter></function></tool_call>`
- **THEN** the recovered tool call has `function.name="ls"` and `function.arguments=json.dumps({"path": "/tmp", "long": "true"})`

#### Scenario: Element-form function with JSON arguments

- **WHEN** the block is `<tool_call><function_name>fetch</function_name><arguments>{"url": "https://example.com", "timeout": 30}</arguments></tool_call>`
- **THEN** the recovered tool call has `function.name="fetch"` and `function.arguments=json.dumps({"url": "https://example.com", "timeout": 30})`

#### Scenario: Nested-object JSON arguments are not truncated

- **WHEN** the block carries `<arguments>{"server": {"host": "localhost", "port": 8080}, "retries": 3}</arguments>`
- **THEN** the parser captures the full object including the nested `{"host": "localhost", "port": 8080}` (not just up to the first inner `}`) and the recovered `function.arguments` round-trips via `json.loads` to the original dict

#### Scenario: Verbose parameter form

- **WHEN** the block uses `<parameter><name>key</name><value>val</value></parameter>` for arguments
- **THEN** the parser still extracts `{"key": "val"}`

#### Scenario: Malformed block is skipped, recovery event records the failure

- **WHEN** a `<tool_call>` block is present but the function name cannot be extracted by any supported form
- **THEN** that block is skipped, `tool_call_recovery_failed` is emitted with a truncated sample of the block, and any other well-formed blocks in the same response are still recovered

#### Scenario: Mixed recovered and failed blocks emit both events

- **WHEN** `reasoning_content` contains two `<tool_call>` blocks of which one is well-formed and the other is unparseable
- **THEN** `tool_call_recovered_from_reasoning` is emitted carrying the rescued call AND `tool_call_recovery_failed` is emitted carrying the diagnostic sample of the unparseable block; the rescued call still reaches the agents-SDK

#### Scenario: Truncated opener without closing tag emits recovery-failed

- **WHEN** `reasoning_content` contains `<tool_call><function=foo` with no closing `</tool_call>` (generation cut off mid-block, no closed regex match)
- **THEN** `tool_call_recovery_failed` is emitted with `match_count` equal to the count of `<tool_call>` substrings (≥ 1) and a `sample` taken from the first opener onwards so operators can see the truncation shape; the response itself passes through

### Requirement: tool_call_recovered_from_reasoning event emitted on rescue

The task-runner SHALL emit a `tool_call_recovered_from_reasoning` event to the task transcript on every chat-completion response where at least one tool call was successfully parsed from `reasoning_content`. The event payload SHALL include:

- `model`: the `model` field from the response (string).
- `calls_recovered`: count of tool calls recovered (integer).
- `function_names`: list of recovered function names in order (list of strings).

When XML markup is detected but no block could be parsed, the runner SHALL instead emit `tool_call_recovery_failed` with:

- `model`: the `model` field from the response (string).
- `match_count`: number of `<tool_call>` substrings found (integer; `0` for the dangling-closer case).
- `sample`: a truncated sample (≤ 256 characters) of the unparseable content for diagnostics.

The runner SHALL ALSO emit `tool_call_recovery_failed` when `reasoning_content` contains a `</tool_call>` substring without any matching `<tool_call>` opener (a dangling-closer pattern observed when the model emits closing scaffolding only). In this case `match_count` is `0` and the `sample` SHALL be a ≤ 256-character window centred on the first `</tool_call>` so operators can see the surrounding context. No recovery is attempted — there is no function name to invoke.

#### Scenario: Successful rescue emits the recovered event

- **WHEN** the post-processor recovers two tool calls (`ls`, `cat`) from a response from model `qwen3.6-35b-a3b-ud-mlx`
- **THEN** the transcript receives a `tool_call_recovered_from_reasoning` event with `model="qwen3.6-35b-a3b-ud-mlx"`, `calls_recovered=2`, `function_names=["ls", "cat"]`

#### Scenario: Failed parse emits the recovery-failed event

- **WHEN** `reasoning_content` contains a `<tool_call>` marker but the parser cannot extract a function name from any block
- **THEN** the transcript receives a `tool_call_recovery_failed` event with the model, the marker count, and a sample of the content

#### Scenario: Dangling closing tag without opener emits recovery-failed

- **WHEN** `reasoning_content` contains `</tool_call>` (and typically `</function>`, `</parameter>`) but no opening `<tool_call>` substring
- **THEN** the transcript receives a `tool_call_recovery_failed` event with `match_count=0` and a `sample` window centred on the first `</tool_call>` so operators can quantify the pattern; the response itself passes through and the existing empty-response handling proceeds

### Requirement: No-progress loop detection (stall guard)

The task runner SHALL detect a no-progress loop within a single agent attempt and
abort it, rather than letting a stuck run consume the full `MAX_TURNS` budget. A
no-progress loop is defined as the same tool being called with byte-identical
arguments repeatedly.

The runner SHALL maintain, per agent attempt, a count of tool-call signatures
where a signature is the tool name combined with its canonicalised arguments
(JSON with sorted keys; a stable fallback when the arguments are not
JSON-serializable). Argument key ordering SHALL NOT affect the signature, and
distinct tools or distinct arguments SHALL be counted independently.

When a single signature's count reaches the configured limit
(`STALL_REPEAT_LIMIT`, default 6), the runner SHALL abort the run as a stall. The
limit SHALL be operator-configurable via the `STALL_REPEAT_LIMIT` environment
variable; a value `<= 0` SHALL disable the guard entirely, and an unparseable
value SHALL fall back to the default with a logged warning. A fresh detector
SHALL be used for each agent attempt so that a legitimate retry starts with a
clean count.

A stall abort SHALL NOT be retried: the runner SHALL record the task as `failed`
with an error classified as `stalled` and exit non-zero, because the same prompt
and model would reproduce the loop. The offending tool call SHALL remain visible
in the transcript (the guard is evaluated after the `tool_call` event is emitted).

#### Scenario: Identical repeats trip the guard

- **WHEN** an agent attempt calls the same tool with byte-identical arguments
  `STALL_REPEAT_LIMIT` times
- **THEN** the run is aborted with a `stalled` error and is not retried

#### Scenario: Varied work does not trip the guard

- **WHEN** an agent calls the same tool with different arguments each time (e.g.
  different file paths or URLs)
- **THEN** each distinct signature is counted independently and the guard does not
  trip

#### Scenario: Argument order is not significant

- **WHEN** the same tool is called with the same argument keys in a different order
- **THEN** the calls share one signature and count toward the same limit

#### Scenario: Guard is disable-able

- **WHEN** `STALL_REPEAT_LIMIT` is set to `0` or a negative value
- **THEN** the stall guard never trips, regardless of how many identical calls occur

#### Scenario: Retry starts with a clean budget

- **WHEN** an agent attempt fails for a retryable reason and a new attempt begins
- **THEN** the stall count from the previous attempt does not carry over

