## 1. submit_result function tool

- [x] 1.1 Add `submit_result` function_tool to `task-runner/main.py` (or `tool_registry.py`) — accepts `result` (str), `status` (str, default "completed"), `questions` (list[str], default []), stores in run context, returns confirmation message
- [x] 1.2 Extend `ToolVisibilityContext` (or add a sibling context dataclass) to carry the submitted result state (`submitted_result: dict | None`)
- [x] 1.3 Register `submit_result` as a native tool on the Agent alongside `discover_tools` and `execute_command`

## 2. Agent loop output extraction

- [x] 2.1 Update the agent loop output extraction to check `submitted_result` from the run context first, before falling back to `result.final_output` text parsing
- [x] 2.2 When `submit_result` was used, construct the callback payload and stdout output directly from the stored fields (skip `extract_json` and `model_dump_json`)
- [x] 2.3 Keep the existing text-based JSON extraction (`extract_json`) and raw text fallback as secondary paths when `submit_result` was not called

## 3. Empty-response nudge

- [x] 3.1 After detecting empty output (no `submit_result`, empty `final_output`), check whether the agent called any tools during the run by inspecting `result.new_items` for `tool_call_output_item` entries
- [x] 3.2 If tools were called, inject a follow-up user message prompting the agent to call `submit_result` and re-run the agent for one additional attempt (does not count toward `MAX_AGENT_RETRIES`)
- [x] 3.3 If the nudge attempt also fails (or no tools were called), fall through to the existing error/exit(1) path

## 4. System prompt updates

- [x] 4.1 Rewrite `OUTPUT_INSTRUCTIONS` to instruct models to call `submit_result()` as the primary output mechanism, with JSON text as a fallback
- [x] 4.2 Add explicit differentiation between `retain` (memory for future tasks) and `submit_result` (delivers result to user)
- [x] 4.3 Add guidance that every task should call `retain` before `submit_result` to build persistent memory

## 5. Tests

- [x] 5.1 Test `submit_result` tool stores result in context and returns confirmation
- [x] 5.2 Test output extraction priority: submit_result > text JSON > raw text > empty
- [x] 5.3 Test empty-response nudge triggers when tools were called but no output produced
- [x] 5.4 Test nudge does not trigger when no tools were called
- [x] 5.5 Test nudge is capped at one attempt
- [x] 5.6 Test backward compatibility: text-based JSON output still works when submit_result is not called
- [x] 5.7 Test multiple submit_result calls — last call wins
