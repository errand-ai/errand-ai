## Context

The task-runner's only shell-execution tool is `execute_command`, a `@function_tool` defined at `task-runner/main.py:408`. It is an always-on native (added to `always_on_tools` at agent construction; never appears in the `<available_mcp_tools>` catalog because catalog entries are only generated from MCP servers).

The model knows shell execution exists from inline guidance in the system prompt (`FILE_TOOL_GUIDANCE` mentions "execute_command for non-file operations" at `main.py:202`) — not from a fresh tool listing. Less-capable models reach for whichever 1–2-word shell verb is most common in their training data:

```
Model's intent: "I need to run `gws drive list …`"
Model's guess: run_command(command="...")   ← Continue.dev convention
              bash(command="...")            ← Anthropic computer-use convention
              shell(command="...")           ← generic
              sh(command="...")              ← POSIX

Actual tool:   execute_command(command="...")
```

The OpenAI Agents SDK raises `ModelBehaviorError("Tool <name> not found in agent TaskRunner")`. The PR #178 auto-recovery handler in `main.py:1489-1500` matches the unknown name against `all_known_tools` and re-enables on a hit — but the alias names aren't in `all_known_tools` (or anywhere else the agent could discover), so recovery fails. The task-manager spawns a fresh runner, the new model run guesses the same wrong name, and the failure loops.

PR #178 made *known but disabled* native tools self-healing. PR #180 made *known skills probed as tools* self-healing. This change makes *common alternative names for the shell tool* self-healing — same defensive-recovery philosophy.

## Goals / Non-Goals

**Goals:**
- Calling `run_command`, `bash`, `shell`, or `sh` succeeds with identical behaviour to calling `execute_command`.
- The canonical name `execute_command` remains the documented one in prompts, file-tool guidance, structured event logs, and all existing tests.
- Structured tool-call events log the alias name the model actually used (e.g. `{"tool": "run_command", ...}`), preserving signal about which aliases fire in production so we can extend or trim the list later.
- Zero impact on the catalog footprint or on prompt size — aliases are always-on natives, never displayed in `<available_mcp_tools>`.
- No prompt scolding ("don't use bash, use execute_command"), no negative instructions — weak models miss those.

**Non-Goals:**
- Renaming `execute_command` to a more common name (rejected — breaks existing specs, tests, and recovery code).
- General Levenshtein-based fuzzy matching for any unknown tool (rejected — too easy to mis-route a typo into the wrong tool).
- Adding aliases for `read_file`, `write_file`, `edit_file`, `discover_tools`, `submit_result` (rejected — those names are already common; no production evidence of hallucination).
- A user-configurable alias list (rejected — premature; the closed set covers the observed cases).

## Decisions

### Decision 1: Register aliases as separate `@function_tool` shims

**Choice:** Each alias (`run_command`, `bash`, `shell`, `sh`) is defined in `task-runner/main.py` as its own `@function_tool(name_override="<alias>")` function with the same signature as `execute_command`. Each shim body calls the same underlying implementation as `execute_command`.

**Alternative considered:** A single ModelBehaviorError recovery path that rewrites the tool name and retries.

**Rationale:** The agents SDK already raises and discards the call args at the point ModelBehaviorError fires. A rewrite-on-error path would force the model to re-issue the call (because the args have been thrown away) and is fragile — the model might re-issue with the same wrong name. A real native tool delegates correctly on the *first* attempt, so the model never sees the error. Cleaner, lower-risk, and uses an SDK feature (`name_override`) designed for exactly this purpose.

### Decision 2: Extract a shared `_execute_command_impl(command, working_directory) -> str` helper

**Choice:** Move the body of `execute_command` into an undecorated helper `_execute_command_impl(command: str, working_directory: str) -> str`. The canonical `execute_command` becomes a thin `@function_tool` that calls the helper; each alias does the same with `name_override="<alias>"`.

**Alternative considered:** Have each alias call `execute_command(command, working_directory)` directly.

**Rationale:** `execute_command` after decoration is a `FunctionTool` object, not a callable Python function — calling it directly may not work or may double-wrap behaviour (logging, error handling, the SDK's `FunctionTool.on_invoke_tool` path). Delegating to an undecorated helper avoids any reflection/decoration weirdness and keeps test-friendliness: the helper can be unit-tested without needing the agents SDK.

### Decision 3: Alias list is a module-level constant (not a setting)

**Choice:** `EXECUTE_COMMAND_ALIASES: tuple[str, ...] = ("run_command", "bash", "shell", "sh")` lives next to `execute_command` in `main.py`. Adding/removing aliases requires a code change.

**Alternative considered:** Reading the list from an env var or settings table.

**Rationale:** The list is small, slow-changing, and security-sensitive (each entry expands the shell-execution surface). A code change forces review. Operationally simpler than a settings round-trip. If a new common alias name appears in production logs, the cost of adding it is one constant edit.

### Decision 4: Aliases are always-on; never displayed in the catalog or system prompt

**Choice:** Aliases are appended to the `native_tools` list passed to `Agent(tools=...)`, and their names are added to `always_on_tools` so they are visible to the filter on every turn. The system prompt continues to mention only `execute_command` (no change to `FILE_TOOL_GUIDANCE`). The `<available_mcp_tools>` catalog is unaffected (it only lists MCP-server tools).

**Rationale:** Listing aliases would clutter the prompt and *encourage* the model to use varied names, which makes the production tool-call telemetry noisier. Aliases are a stealth compatibility surface — they exist so the model that already reaches for `run_command` succeeds, not to advertise alternative names to the model.

### Decision 5: Aliases emit `tool_call` events with the alias name, not the canonical name

**Choice:** When the model calls `run_command(command="ls")`, the structured `tool_call` event in `task_event_logs:{task_id}` is `{"tool": "run_command", "args": {"command": "ls"}}`. The `tool_result` event likewise carries `tool: "run_command"`. This falls out naturally from the SDK emitting events under each tool's registered name.

**Rationale:** Preserves operator visibility into which alias fired. If `bash` never fires in production over 30 days, we can drop it; if a new alias appears in `Not found:` logs, we can add it. Renaming alias events to the canonical name would hide that signal.

## Risks / Trade-offs

- **[Risk] Expanding shell-execution under 4 names increases audit surface.** → Mitigation: all four aliases share the same `_execute_command_impl`, so authorisation, output capping, and timeout behaviour are identical to the canonical tool. The alias list is a single module constant, easy to inventory.

- **[Risk] Future tool additions might need similar alias coverage.** → Acceptable: pattern is documented (extract a `_<name>_impl` helper, register aliases via `name_override`). Cost per future tool ≈ 5 lines.

- **[Risk] An alias name collides with an MCP server tool of the same name.** → Mitigation: always-on classification already wins over catalog membership in `discover_tools` (precedence enforced in `tool_registry.py`). The alias `bash` would never collide with an MCP tool called `bash` in a way that breaks behaviour — the alias would simply mask the MCP tool. If any MCP server later exposes a `bash` tool with different semantics, the operator will see it in `Not found: bash` recovery telemetry and can rename the alias.

- **[Trade-off] The system prompt does not advertise `run_command`/`bash`/etc.** → Strong models stay on `execute_command` (good — keeps logs clean). Weak models that reach for an alias succeed silently. Operators see alias usage in `tool_call` events.

- **[Risk] Adding tools may bloat the LLM tool-schema payload sent every turn.** → Each alias adds ~80 bytes of schema. Four aliases ≈ 320 bytes vs total prompt size in tens of KB. Negligible.

## Migration Plan

Single PR, no data migration, no breaking changes:

1. Extract `_execute_command_impl(command, working_directory) -> str` from the current `execute_command` body in `main.py:408-499` (or wherever it ends).
2. Replace `execute_command`'s body with `return _execute_command_impl(command, working_directory)`.
3. Define `EXECUTE_COMMAND_ALIASES: tuple[str, ...] = ("run_command", "bash", "shell", "sh")`.
4. Define an alias factory `_make_execute_command_alias(name: str)` that returns a `@function_tool(name_override=name)`-decorated function with identical signature and body (`return _execute_command_impl(...)`).
5. Generate alias shims at module load: `EXECUTE_COMMAND_ALIAS_TOOLS = [_make_execute_command_alias(n) for n in EXECUTE_COMMAND_ALIASES]`.
6. In agent construction (`main.py:1335`), extend `native_tools` with `EXECUTE_COMMAND_ALIAS_TOOLS`; `always_on_tools` is rebuilt from the (now longer) list automatically.
7. Add tests covering each alias name, parameter parity, and tool-call event naming.

Rollback: revert the PR. No persistent state involved.

## Open Questions

- None. The alias list is intentionally short; further additions are a follow-up driven by production telemetry.
