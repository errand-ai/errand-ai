## Why

Non-premiere local models (qwen3-family observed on LMStudio, but the pattern recurs across other open-weights releases) emit tool calls inside `reasoning_content` as Qwen-XML markup rather than in the structured `tool_calls` field. A concrete example captured from LiteLLM's response log for `qwen3.6-35b-a3b-ud-mlx`:

```json
{
  "choices": [{
    "message": {
      "content": "",
      "tool_calls": null,
      "reasoning_content": "The /tmp directory isn't accessible. Let me use a path within the workspace instead.\n\n<tool_call>\n<function=execute_command>\n<parameter=command>\ngws drive files get --params '{...}' --output /workspace/verify_report.md\n</parameter>\n</function>\n</tool_call>"
    },
    "finish_reason": "stop"
  }],
  "usage": { "completion_tokens": 0, "completion_tokens_details": { "reasoning_tokens": 103 } }
}
```

The model produced a perfectly good tool call, but it landed in the wrong field. The agents-SDK reads `tool_calls`, sees `null`, sees empty `content`, and raises `EmptyResponseError`. The task fails — and on repeating tasks the same shape recurs every retry, so the failure is persistent.

This problem is **not specific to one model**. The same dialect mismatch hits other open-weights models served via LMStudio when their chat-template tool-call parser is misconfigured or absent. Fixing it per-model (chat template tweaks, LiteLLM model-param flags) is unsustainable.

## What Changes

- The task-runner SHALL post-process every chat-completion response from `AsyncOpenAI` before the agents-SDK consumes it. When the response shape matches "empty content + null tool_calls + non-empty reasoning_content containing `<tool_call>` XML markup", the runner SHALL parse the XML, build OpenAI-shaped `ChatCompletionMessageToolCall` objects, mutate the response so `choices[0].message.tool_calls` is the parsed list, and let the agents-SDK proceed as if the model had emitted a proper tool call.
- The parser SHALL handle the Qwen-XML dialect variants seen in the wild: `<function=name>` form with `<parameter=key>value</parameter>` children, and the alternative `<function_name>name</function_name>` form. JSON-blob argument bodies (`<arguments>{...}</arguments>`) SHALL also be supported.
- Responses that do not match the dialect SHALL pass through untouched. The post-processor SHALL never reject or mangle valid responses.
- A new event `tool_call_recovered_from_reasoning` SHALL be emitted to the task transcript on every successful rescue, so operators can spot which models exhibit this behaviour and how often.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `task-runner-error-resilience`: extend with a "recover XML tool calls from reasoning_content" requirement covering detection, parsing, response mutation, pass-through fallback, and the recovery event.

## Impact

- **Code**: `task-runner/main.py` (new wrapper around `AsyncOpenAI.chat.completions.create`, new parser module, integration in `main()` where the client is constructed at line 1639).
- **Tests**: new `task-runner/tests/test_xml_tool_call_recovery.py` covering the parser, the wrapper passthrough, and the event emission.
- **Telemetry**: new `tool_call_recovered_from_reasoning` event.
- **Settings**: no new settings; behaviour is always-on.
- **Backwards compatibility**: existing well-behaved responses are unaffected (the wrapper short-circuits when `content`, `tool_calls`, or absence of `<tool_call>` markup makes recovery unnecessary).
- **Out of scope**: fixing the upstream models' chat templates, LiteLLM-side tool-parse hooks, the LMStudio prompt-cache eviction churn, and any other dialect (e.g. Claude-style tool use, vendor-specific JSON-in-content fallbacks).
