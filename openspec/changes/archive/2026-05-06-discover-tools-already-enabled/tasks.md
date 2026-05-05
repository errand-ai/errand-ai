## 1. Track always-on tool names in the visibility context

- [x] 1.1 Add `always_on_tools: set[str]` field to `ToolVisibilityContext` in `task-runner/tool_registry.py`, defaulting to an empty set
- [x] 1.2 In `task-runner/main.py`, populate `always_on_tools` from the names of the native `@function_tool` callables attached to the agent (single source of truth — derive from the same list used for `tools=[...]`)

## 2. Update `discover_tools` classification

- [x] 2.1 Modify `discover_tools` in `task-runner/tool_registry.py` to classify each name into `enabled` / `already_on` / `not_found`, with always-on taking precedence over catalog membership
- [x] 2.2 Build the response by joining clauses in the order `Enabled` → `Already enabled (always-on)` → `Not found`, separated by `". "`
- [x] 2.3 Update the `discover_tools` docstring if it mentions only the two-outcome shape

## 3. Tests

- [x] 3.1 Add a unit test in `task-runner/test_tool_registry.py` covering a probe for an always-on tool only — expects `Already enabled (always-on): read_file`
- [x] 3.2 Add a unit test for the mixed case (catalog + always-on + unknown) — expects all three clauses joined in the documented order
- [x] 3.3 Add a unit test confirming `enabled_tools` is unchanged when the only requested name is always-on
- [x] 3.4 Add a unit test for the precedence case: a name in both `always_on_tools` and `all_known_tools` is reported under `Already enabled (always-on)` and not under `Enabled`
- [x] 3.5 Verify the existing "Not found" scenario still passes for genuinely unknown names

## 4. Verify end-to-end

- [x] 4.1 Run `errand/.venv/bin/python -m pytest task-runner/test_tool_registry.py -v` and confirm all tests pass
- [x] 4.2 Run the full task-runner test suite to confirm no regressions
- [x] 4.3 Bump `VERSION` (patch increment) and update CLAUDE.md only if the task-runner section needs adjustment

## 5. Archive

- [x] 5.1 Mark all tasks complete and archive the change via `/opsx:archive`
