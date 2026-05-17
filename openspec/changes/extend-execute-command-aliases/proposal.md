# Extend execute_command aliases — cover `executescript` and Harmony-format suffixes

## Why

PR #181 (`alias-known-tool-name-mistakes`, archived as `2026-05-17-alias-known-tool-name-mistakes`) shipped a static alias set covering four shell-tool name hallucinations: `run_command`, `bash`, `shell`, `sh`. Production logs from 2026-05-17 show two new failure modes that the existing alias set does not catch:

1. **`executescript`** — observed in tasks `68022ee9-ae4b-426f-982b-7b742bf172ca` and earlier; the model calls a tool named `executescript` that does not exist. Auto-recovery (PR #178) cannot rescue it because `executescript` is not in `all_known_tools`. The task-runner loops, wasting LLM turns until it times out.

2. **Harmony-format token leakage** — observed in task `7bbc189f-abf5-4c30-93f6-f7a938197445` with tool calls like `run_command<|channel|>json`. The OpenAI Harmony format token (`<|channel|>...`) bleeds into the tool name string the model emits. Even though `run_command` IS aliased, the SDK does exact-match lookup, so `run_command<|channel|>json` is not found.

Both failures look identical to the user: the agent thrashes on `gws drive` (or any other shell-tool need), never produces output, and burns LLM time before the runner gives up.

## What changes

- **`task-runner/main.py`** — extend `EXECUTE_COMMAND_ALIASES` to add `executescript`. (Optionally `execute_script`, `python` — to be decided in design.)
- **`task-runner/main.py`** — extend the existing `ModelBehaviorError` recovery handler (the path that catches "Tool X not found in agent TaskRunner") to **normalize** the failing tool name before re-dispatching: if the name contains a Harmony-format suffix (`<|channel|>...`, `<|...|>`, or any `<|`-prefixed token), strip the suffix and re-attempt with the bare name. If the bare name is in `all_known_tools` or `EXECUTE_COMMAND_ALIASES`, treat the original call as the bare-name call.
- **Spec delta** — `openspec/specs/lazy-mcp-tool-registry/spec.md` requirement *"execute_command alias tools for common name hallucinations"* is amended to include `executescript` in the minimum alias set, and a new requirement is added covering Harmony-suffix normalization.
- **Tests** — unit tests for both the alias addition and the Harmony stripper, plus a regression test that an `executescript` call dispatches the same body as `execute_command`.

## Impact

- **Affected specs**: `lazy-mcp-tool-registry` (amend one requirement, add one)
- **Affected code**: `task-runner/main.py` (alias list + recovery handler), `task-runner/test_main.py` (new tests)
- **Risk**: low — additive, pure compatibility shim, no behaviour change for clients that use the canonical names
- **Version bump**: PATCH (additive, backwards-compatible)
- **Deployment**: standard — CI rebuilds task-runner image, ArgoCD picks up new tag on merge
