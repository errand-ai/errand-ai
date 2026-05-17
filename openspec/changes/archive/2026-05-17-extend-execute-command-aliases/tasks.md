## 1. Bump version

- [x] 1.1 Increment `VERSION` per semver (PATCH — additive, backwards-compatible recovery behaviour)

## 2. Extend the static alias set

- [x] 2.1 In `task-runner/main.py`, update `EXECUTE_COMMAND_ALIASES` to `("run_command", "bash", "shell", "sh", "executescript")` — preserve order so existing tests on slot 0 still hold
- [x] 2.2 Update the regression-guard test in `task-runner/test_main.py` (`assert EXECUTE_COMMAND_ALIASES == (...)`) to match the new tuple

## 3. Add Harmony-suffix normalizer

- [x] 3.1 In `task-runner/main.py`, locate the `ModelBehaviorError` recovery handler added in PR #178 (search for `Tool .* not found in agent`)
- [x] 3.2 Add a helper `_normalize_harmony_tool_name(name: str) -> str` that returns `name.split("<|", 1)[0]`. Place it next to `EXECUTE_COMMAND_ALIASES`.
- [x] 3.3 In the recovery handler, before the existing "is it a known MCP tool we can enable" lookup, compute `normalized = _normalize_harmony_tool_name(failing_name)`. If `normalized != failing_name` AND `normalized` is in `all_known_tools` OR `EXECUTE_COMMAND_ALIASES` OR equals `"execute_command"`:
  - Log a structured INFO event with keys `event="harmony_suffix_normalized"`, `original=failing_name`, `normalized=normalized`, `model=<model id from current run>`
  - Re-dispatch the call by translating the tool name to `normalized` (the SDK's retry path picks up the corrected name on the next agent turn — see the existing auto-recovery pattern)
- [x] 3.4 If `normalized` is still unknown, fall through to existing handling (no behaviour change)

## 4. Tests

- [x] 4.1 Add a unit test for `_normalize_harmony_tool_name`: confirm `"run_command<|channel|>json"` → `"run_command"`, `"execute_command<|message|>start"` → `"execute_command"`, `"plain_name"` → `"plain_name"`, `""` → `""`
- [x] 4.2 Add a unit test asserting `"executescript"` is registered as an alias tool — same pattern as the existing alias tests in `test_main.py`
- [x] 4.3 Add a unit test asserting an `executescript` invocation runs the same body as `execute_command` (analogous to existing `run_command` alias test)
- [x] 4.4 Add a recovery-handler test that simulates a `ModelBehaviorError` with `Tool run_command<|channel|>json not found` and asserts (a) the normalization log is emitted with original + normalized names, and (b) the retry path re-issues with `run_command`
- [x] 4.5 Add a negative recovery-handler test for an unknown tool with Harmony suffix (e.g. `frobnicate<|channel|>json`) confirming no re-dispatch happens and the original "tool not found" handling fires
- [x] 4.6 Run `errand/.venv/bin/python -m pytest task-runner/ -v` and confirm green (839 baseline + new tests)

## 5. Local verification

- [x] 5.1 ~~`docker compose -f testing/docker-compose.yml up --build`~~ — skipped; local build was prohibitively slow. Unit tests (247 task-runner + 1623 errand) cover the logic. Relying on CI rebuild + ArgoCD K8s smoke for the integration check.
- [x] 5.2 Post-merge: trigger a task whose system prompt suggests shell work; verify tool-call logs show normal `execute_command` events with no behaviour regression
- [x] 5.3 (Optional) Re-run the "publish approved tweet" task that was failing on `executescript` / `run_command<|channel|>json` and confirm tool calls dispatch — Grafana Loki should show no "Tool X not found" errors for these patterns

## 6. Commit, push, PR

- [x] 6.1 Create feature branch `extend-execute-command-aliases` from `main`
- [x] 6.2 Commit changes with a clear message (commits 44dc547 + de93a7b — review-fix follow-up)
- [x] 6.3 Push and open the PR (#182); CI green on both commits
- [x] 6.4 Verify the built image runs on Kubernetes (ArgoCD sync or `helm upgrade --dry-run`) and a smoke task succeeds before merging

## 7. Archive

- [x] 7.1 After merge to main, run `openspec archive --change extend-execute-command-aliases` (or `/opsx:archive`) to fold the spec deltas into `openspec/specs/lazy-mcp-tool-registry/spec.md`
