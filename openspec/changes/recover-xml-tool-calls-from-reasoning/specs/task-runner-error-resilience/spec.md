## ADDED Requirements

### Requirement: Recover XML-shaped tool calls emitted in reasoning_content

The task-runner SHALL wrap `client.chat.completions.create` (where `client` is the `AsyncOpenAI` instance constructed at startup and registered via `set_default_openai_client`) with a post-processor that inspects every chat-completion response before returning it to the agents-SDK. When the response shape matches:

1. `choices[0].message.content` is `""` or `None`, AND
2. `choices[0].message.tool_calls` is `None` or `[]`, AND
3. `choices[0].message.reasoning_content` is a non-empty string, AND
4. `reasoning_content` contains at least one `<tool_call>` substring

then the post-processor SHALL parse the Qwen-XML tool-call blocks from `reasoning_content`, construct OpenAI-shaped `ChatCompletionMessageToolCall` entries, and mutate the response so `choices[0].message.tool_calls` is the list of recovered calls. The agents-SDK SHALL then proceed as if the model had emitted a proper tool-calling response.

Responses that fail any of the four conditions SHALL be returned unchanged. The post-processor SHALL NOT touch `usage`, `finish_reason`, or any field other than `choices[0].message.tool_calls`.

The post-processor SHALL be active for every chat completion the runner makes — there is no opt-out setting.

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

### Requirement: Qwen-XML tool-call parser supports common dialect variants

The parser SHALL recognise the following Qwen-XML variants when extracting a tool call from a `<tool_call>...</tool_call>` block:

**Function name** — first matching form wins:
- `<function=NAME>...</function>` (attribute form)
- `<function_name>NAME</function_name>` (element form)

**Arguments** — first matching form wins:
- `<arguments>{...JSON...}</arguments>` — JSON blob; parsed via `json.loads`
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

#### Scenario: Verbose parameter form

- **WHEN** the block uses `<parameter><name>key</name><value>val</value></parameter>` for arguments
- **THEN** the parser still extracts `{"key": "val"}`

#### Scenario: Malformed block is skipped, recovery event records the failure

- **WHEN** a `<tool_call>` block is present but the function name cannot be extracted by any supported form
- **THEN** that block is skipped, `tool_call_recovery_failed` is emitted with a truncated sample of the block, and any other well-formed blocks in the same response are still recovered

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
