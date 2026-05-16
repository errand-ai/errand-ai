## 1. Bump version

- [x] 1.1 Increment `VERSION` per semver (PATCH — additive, backwards-compatible recovery behaviour)

## 2. Refactor execute_command into a helper + thin wrapper

- [x] 2.1 In `task-runner/main.py`, extract the body of the current `execute_command` function into an undecorated module-level helper `_execute_command_impl(command: str, working_directory: str = "/workspace") -> str` (same signature, same behaviour, same output truncation/timeout/error-formatting)
- [x] 2.2 Replace `execute_command`'s body so it delegates: `return _execute_command_impl(command, working_directory)` (the `@function_tool` decoration on `execute_command` stays exactly as-is)

## 3. Define and generate alias shims

- [x] 3.1 Add module-level constant `EXECUTE_COMMAND_ALIASES: tuple[str, ...] = ("run_command", "bash", "shell", "sh")` next to `execute_command`
- [x] 3.2 Add an alias factory `_make_execute_command_alias(name: str)` that returns a `@function_tool(name_override=name)`-decorated function with signature `(command: str, working_directory: str = "/workspace") -> str` whose body returns `_execute_command_impl(command, working_directory)`. Reuse `execute_command`'s docstring (with a leading note that the alias delegates) so the schema sent to the LLM is informative.
- [x] 3.3 Generate the alias tool list at module load: `EXECUTE_COMMAND_ALIAS_TOOLS = [_make_execute_command_alias(n) for n in EXECUTE_COMMAND_ALIASES]`

## 4. Wire aliases into the agent

- [x] 4.1 In agent construction (`main.py`, around the `native_tools = [...]` assignment near line 1335), extend `native_tools` with `EXECUTE_COMMAND_ALIAS_TOOLS` so every alias is attached to `Agent(tools=...)`
- [x] 4.2 Verify `always_on_tools = {t.name for t in native_tools}` (existing line) now naturally contains every alias name — no separate change required
- [x] 4.3 Log the alias list once at startup (info-level) so operators can confirm which aliases are armed in production

## 5. Tests

- [x] 5.1 Add a unit test for `_execute_command_impl` directly: a trivial command (`echo alias-test`) returns expected output (uses the existing subprocess; isolates the helper from any `@function_tool` decoration)
- [x] 5.2 Add a unit test asserting `EXECUTE_COMMAND_ALIASES` is exactly `("run_command", "bash", "shell", "sh")` (regression guard against accidental list shrink/typo)
- [x] 5.3 Add a unit test asserting each generated alias tool's `.name` matches the alias string (verifies `name_override` reached the SDK correctly)
- [x] 5.4 Add a unit test asserting each generated alias tool is included in the `native_tools` list passed to `Agent(...)` — covered by a fixture that calls the same construction path as `main.py` and inspects the resulting `always_on_tools` set
- [x] 5.5 Add a `discover_tools` test: probing `["run_command"]` when `run_command` is in `always_on_tools` returns `Already enabled (always-on): run_command` and does not mutate `enabled_tools` (regression guard that aliases interact correctly with the existing precedence rules)
- [x] 5.6 Run `errand/.venv/bin/python -m pytest task-runner/ -v` and confirm green; in particular, confirm no existing test breaks because `execute_command` was refactored

## 6. Local verification

- [ ] 6.1 `docker compose -f testing/docker-compose.yml up --build` — start the stack
- [ ] 6.2 Run a task that exercises shell (e.g. trigger a task whose system prompt suggests running a CLI tool); inspect tool-call logs — `execute_command` events should look identical to before
- [ ] 6.3 (Optional, for stronger evidence) Force-trigger an alias by inspecting a task where the model has historically called `run_command` (the "Publish Approved Tweet" task on glm-4-flash, per Loki) and confirm the `tool_call` event now carries `{"tool": "run_command", ...}` and the task succeeds

## 7. Commit, push, PR

- [ ] 7.1 Create feature branch `alias-known-tool-name-mistakes` from `main` (after PR #180 is merged, so this branch starts from the post-skill-aware-discover-tools state)
- [ ] 7.2 Commit changes with a clear message (subject ≤ 72 chars, body explaining the hallucination pattern, the alias set, and the production task evidence)
- [ ] 7.3 Push and open the PR; wait for CI to build images + Helm chart
- [ ] 7.4 Verify the built image runs on Kubernetes (ArgoCD sync or `helm upgrade --dry-run`) and a smoke task succeeds before merging
