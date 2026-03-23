## Why

When weaker models (e.g. gpt-oss:20b) call an MCP tool without first calling `discover_tools`, the OpenAI Agents SDK raises a `ModelBehaviorError` ("Tool X not found in agent TaskRunner") and the entire task fails. The model knows the correct tool name from the catalog but skips the discovery ceremony. This wastes all 3 retry attempts since the model repeats the same mistake each time.

## What Changes

- The tool filter will auto-discover known but undiscovered tools at filter evaluation time instead of rejecting them. When a model calls a tool that exists in `all_known_tools` but hasn't been discovered yet, the filter will silently add it to `enabled_tools` and allow the call to proceed, logging a warning for observability.
- This makes lazy tool loading a transparent optimization rather than a hard gate — models that follow the protocol save prompt tokens by not loading unused tool schemas, but models that skip discovery still work.

## Capabilities

### New Capabilities

_None — this modifies existing behavior._

### Modified Capabilities

- `lazy-mcp-tool-registry`: The tool filter will auto-enable known-but-undiscovered tools instead of blocking them, adding a fallback path for models that skip `discover_tools`.

## Impact

- `task-runner/tool_registry.py`: `create_tool_filter` — modify the filter function to auto-enable instead of returning `False`
- `task-runner/test_tool_registry.py`: Update/add tests for auto-discovery behavior
- No API changes, no breaking changes, no dependency changes
