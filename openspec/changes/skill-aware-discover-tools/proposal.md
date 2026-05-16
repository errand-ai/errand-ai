## Why

Task-runner sessions on less-capable models frequently call `discover_tools` with skill names (e.g. `tweet-publisher`, `gws-drive`, `blog-to-tweets`) rather than tool names, because the skill manifest and the MCP tool catalog both render as flat "name: description" lists in the system prompt and the imperative *"You MUST call `discover_tools` before using them"* is the loudest signal in the prompt. The current response — `"Not found: <name>"` — reads as terminal to a weak model, which then abandons the task. Production Loki logs show this pattern repeatedly across "Publish Approved Tweet" and similar tasks: tasks `b33a736c-…`, `85f4945f-…`, `a728734e-…`, `24fcd34b-…` all probed skill names through `discover_tools` and failed even though the relevant skill was sitting on disk at `/workspace/skills/<name>/SKILL.md`.

Rather than tiering models as "weak" or "strong" (a label that ages badly and requires an ever-growing list of model IDs to maintain), we recover in-band: when `discover_tools` is called with a name that matches an installed skill, it returns the skill's full `SKILL.md` content instead of `"Not found"`. The mistake becomes self-correcting on the same turn for every model.

## What Changes

- `ToolVisibilityContext` gains an `installed_skills: dict[str, str]` field mapping skill names to absolute `SKILL.md` paths.
- The task-runner populates `installed_skills` at startup by scanning `/workspace/skills/*/SKILL.md`.
- `discover_tools` partitions any names that miss the tool catalog into two buckets: matched-skill and truly-unknown. For matched-skill names it reads the corresponding `SKILL.md` and inlines its contents in the tool result; for truly-unknown names it preserves today's `"Not found: ..."` wording.
- The response format gains a `Loaded skill:` section alongside the existing `Enabled:`, `Already enabled (always-on):`, and `Not found:` sections so a single `discover_tools` call can return a mix of all four outcomes coherently.
- Strong models that never probe skill names through `discover_tools` are unaffected — the new path only fires on a name collision with an installed skill.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `lazy-mcp-tool-registry`: `discover_tools` adds a new recovery behaviour for names matching installed skills, returning the SKILL.md content rather than `"Not found"`. `ToolVisibilityContext` gains the `installed_skills` field needed to drive that behaviour.

## Impact

- **Code**: `task-runner/tool_registry.py` (`ToolVisibilityContext`, `discover_tools`); `task-runner/main.py` (populate `installed_skills` at startup from `/workspace/skills/`).
- **Tests**: `task-runner/test_tool_registry.py` (new cases covering skill match, mixed enable+skill+not-found, and truly-unknown name still returning "Not found").
- **Prompts**: unchanged — the recovery happens at the tool-result layer, not in the system prompt.
- **No DB, API, or Helm changes.**
- **No breaking changes** — `discover_tools` callers that pass only real tool names see identical output.
