## Why

Less-capable models routinely hallucinate the wrong name for the shell tool — calling `run_command(command="gws drive list ...")` when the actual tool is `execute_command`. Production Loki logs (task `294522f3-…`, two consecutive task-runner pods at 2026-05-16T21:55 and 21:57 UTC) show the model issuing `run_command` and the agent raising `ModelBehaviorError: Tool run_command not found in agent TaskRunner`. The existing auto-recovery from PR #178 cannot rescue this case — it only re-enables names already in `all_known_tools`, and `run_command` is not a real tool. The task-manager then spawns a fresh runner, which guesses the same wrong name, and the loop repeats.

Several names are interchangeable in English/training data:

- `run_command` (Continue.dev convention, many OpenAI cookbook examples)
- `bash` / `shell` / `sh` (Anthropic computer-use convention)
- `execute_command` (errand's canonical name)

Rather than rename the canonical tool (which would break specs, logs, and existing recovery code) or try to teach every weak model the right name via prompt scolding, we register the common alias names as lightweight `@function_tool` shims that delegate to `execute_command`. The model can use whichever name it reaches for; the call routes to the same implementation. Mirrors the same defensive-recovery philosophy as PR #178 (always-on tools) and PR #180 (skill-aware `discover_tools`).

## What Changes

- A new module-level dict `EXECUTE_COMMAND_ALIASES = ("run_command", "bash", "shell", "sh")` lives alongside `execute_command` in `task-runner/main.py`.
- For each alias, register a lightweight `@function_tool` shim with the same signature as `execute_command` whose body simply calls `execute_command(...)` and returns its result.
- All alias shims are attached to the agent at construction (added to the `native_tools` list passed to `Agent(tools=...)` and `always_on_tools`), so they are always callable but never displayed in the `<available_mcp_tools>` catalog.
- Aliases are an internal compatibility surface: the canonical name `execute_command` remains the documented one in the system prompt, file-tool guidance, and structured event logs (when an alias fires, the structured `tool_call` event SHALL log the alias name actually called, so the operator can see which alias was used).
- No changes to the prompt, the catalog, the recovery handler, or the user-facing tool surface.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `lazy-mcp-tool-registry`: adds a requirement covering the alias shims — that common alternative names for `execute_command` SHALL be registered as always-on native tools that delegate to it.

## Impact

- **Code**: `task-runner/main.py` (new alias shim functions, extend `native_tools` list).
- **Tests**: `task-runner/test_main.py` or `task-runner/test_tool_registry.py` (each alias resolves to `execute_command`'s output for a fixed input).
- **Prompts**: unchanged.
- **No DB, API, Helm, or breaking changes.** Existing code calling `execute_command` continues to work; the canonical name is preserved.
- **Observability**: aliased calls show up as the alias name in `tool_call` events (e.g. `{"tool": "run_command", ...}`), preserving accurate signal for "which alias did the model reach for" — useful for trimming or extending the alias list later.
