## Why

The task runner agent sometimes produces preamble text before the structured JSON output (e.g. "Based on my analysis... ```json {...}```"), which defeats the current `startswith("```")` fence-stripping logic in both `task-runner/main.py` and `backend/worker.py`. When this happens, JSON parsing fails and the fallback wraps the **entire raw output** (preamble + code fence + JSON) as the result string — so the user sees raw JSON with markdown code fences instead of the actual report. This was observed on the "Check ArgoCD Applications Health" task in production after the agent called ArgoCD MCP tools.

## What Changes

- Improve JSON extraction in the task runner (`task-runner/main.py`) to find and extract a JSON block even when the LLM produces preamble text before the code fence or JSON object
- Apply the same robust extraction logic in the worker (`backend/worker.py`) as a second line of defence
- Add tests covering the preamble-before-JSON edge case in both task runner and worker test suites

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-runner-agent`: Strengthen the structured output extraction to handle preamble text before JSON code fences or bare JSON objects
- `task-worker`: Apply matching robust JSON extraction when the worker parses container stdout, as a fallback layer

## Impact

- **task-runner/main.py**: Output parsing logic (lines 173-191) — extraction must handle text before ```` ```json ```` fences and text before bare `{...}` JSON
- **backend/worker.py**: Markdown fence stripping logic (lines 461-466) — same robust extraction
- **Tests**: `task-runner/test_main.py` and `backend/tests/test_worker.py` need new edge-case scenarios
- No API, database, or frontend changes required — the output field will simply contain clean report text instead of raw JSON with markdown
