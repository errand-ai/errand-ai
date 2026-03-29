## Context

The task-runner uses the OpenAI Agents SDK to run a ReAct agent. Currently, the agent's output is extracted from `result.final_output` — the last text message the model produces. The model is instructed (via `OUTPUT_INSTRUCTIONS` appended to the system prompt) to emit a raw JSON object `{"status": "completed", "result": "...", "questions": []}` as its final text.

This text-based contract is fragile in two ways:

1. **Empty responses**: Models (particularly kimi-k2.5) frequently call `retain()` as their last tool call, then produce an empty final turn — confusing "save to memory" with "deliver result". This accounts for 15/22 task errors over a 4-day sample, each triggering a full container restart + retry.

2. **JSON format corruption**: The result goes through a double-serialization chain (task-runner `model_dump_json()` → Valkey callback → server-side `extract_json()` re-parse). When the JSON contains complex nested content, the re-parsing can fail, causing the raw JSON wrapper to leak into the `output` DB column and display in the frontend.

The task-runner already has native `@function_tool` tools (`discover_tools`, `execute_command`). Adding `submit_result` as another function_tool is a natural extension of the existing architecture.

## Goals / Non-Goals

**Goals:**

- Eliminate the empty-response failure class by giving the model an explicit "I'm done" tool call at the same affordance level as `retain` and other tools
- Eliminate JSON format corruption by separating the result content from the status wrapper at the source (tool call arguments), never requiring text-based JSON parsing
- Add an in-conversation nudge for empty responses to avoid full container restarts when the model forgets to submit
- Maintain backward compatibility with text-based JSON output during transition
- Reinforce in the system prompt that `retain` is for memory and `submit_result` is for output delivery

**Non-Goals:**

- Making `submit_result` an MCP tool (it's a local function_tool — no network round-trip needed)
- Removing `extract_json` entirely (kept as fallback for backward compatibility)
- Changing the server-side result storage format or database schema
- Changing the frontend — it already expects a plain markdown string

## Decisions

### Decision 1: `submit_result` as a native `@function_tool`, not an MCP tool

The tool is implemented as a Python `@function_tool` alongside `discover_tools` and `execute_command` in the task-runner process. It stores the submitted result in the `ToolVisibilityContext` (or a dedicated context object) for the agent loop to pick up after the run completes.

**Why not MCP?** An MCP tool would require a network round-trip to an MCP server, introduce coupling between the task-runner and the backend (two paths for results), and create a coordination problem (MCP records result but task-runner doesn't know to exit). A function_tool is local, instant, and integrates naturally with the existing agent loop.

### Decision 2: Result extraction priority — submit_result > text fallback

After the agent run completes, the agent loop checks for results in this order:
1. **`submit_result` tool call** — if the tool was called during the run, use its captured `result` and `status` directly
2. **Text-based JSON fallback** — if `submit_result` was not called but `result.final_output` contains parseable JSON, extract it (backward compat for models that follow the old instructions)
3. **Raw text fallback** — if neither structured output is found, wrap the raw text as `{"status": "completed", "result": raw_text}`
4. **Empty response handling** — if all of the above yield nothing, trigger the nudge mechanism

### Decision 3: Empty-response nudge before container restart

When the agent produces an empty `final_output` AND `submit_result` was not called, instead of immediately exiting with code 1:
1. Check if the agent called any tools during the run (it did real work)
2. If yes, inject a follow-up user message: "You completed your work but didn't deliver the result. Call submit_result now with your findings."
3. Re-run the agent with the same context for up to 1 additional attempt
4. If the nudge attempt also produces no result, fall back to exit(1) as today

This avoids a full K8s Job restart (container image pull, MCP reconnection, re-reading the prompt) for a recoverable situation.

### Decision 4: Callback posts structured fields, not raw JSON text

Currently the task-runner posts `TaskRunnerOutput.model_dump_json()` to the callback — the full `{"status": "completed", "result": "..."}` wrapper. The server then re-parses it.

With `submit_result`, the task-runner already has the fields separated. The callback payload changes to post the same JSON structure, but constructed from clean, validated fields rather than re-serialized model output. This doesn't change the wire format but ensures the content is always well-formed, eliminating the double-parse failure mode.

### Decision 5: System prompt updates

The `OUTPUT_INSTRUCTIONS` constant is rewritten to:
- Instruct models to call `submit_result(result=..., status=...)` when done
- Explicitly state that `retain` saves to memory for future tasks and does NOT deliver the result
- Keep a brief mention of the JSON fallback format for models that don't follow tool instructions
- Add guidance that every task should call `retain` before `submit_result` to build persistent memory

## Risks / Trade-offs

**[Risk] Models ignore the tool and still emit text JSON** → The text-based fallback handles this transparently. Both paths produce the same end result. Over time, as prompt instructions improve, more models will use the tool.

**[Risk] Nudge mechanism causes infinite loops** → Capped at 1 nudge attempt. If the model fails to submit after the nudge, it falls through to exit(1) as before. The nudge does not count toward `MAX_AGENT_RETRIES`.

**[Risk] `submit_result` called multiple times** → Last call wins. The context stores only the most recent submission. This is documented in the tool description.

**[Risk] Model calls `submit_result` then continues working** → The tool returns a message indicating the result has been submitted. The agent loop uses the submitted result regardless of what happens after. The tool description says "You may now stop."

**[Trade-off] Two output paths (tool + text fallback)** → Adds code complexity but is necessary for backward compatibility. The fallback path is existing code, not new. Can be removed in a future change once all models reliably use the tool.
