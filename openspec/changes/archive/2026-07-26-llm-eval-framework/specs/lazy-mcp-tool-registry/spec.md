## ADDED Requirements

### Requirement: Excluded catalog tools
The task-runner SHALL maintain an excluded-tools set (`EXCLUDED_CATALOG_TOOLS`) of MCP tool names that are administrative and never intended for task LLMs: `clone_task_profile`, `delete_task_profile`, `search_tasks`, `start_eval_run`, `record_eval_result`, `finish_eval_run`, `get_eval_run`. Excluded tools SHALL be omitted from the generated tool catalog, and `discover_tools` SHALL refuse to enable them even when requested by exact name, responding as if the tool does not exist. The auto-enable-on-ModelBehaviorError recovery SHALL likewise never enable an excluded tool.

#### Scenario: Excluded tool absent from catalog
- **WHEN** the task-runner connects to the Errand MCP server which exposes `record_eval_result`
- **THEN** `record_eval_result` does not appear in the `<available_mcp_tools>` catalog block

#### Scenario: discover_tools refuses excluded tool
- **WHEN** the agent calls `discover_tools(tool_names=["search_tasks"])`
- **THEN** `search_tasks` is not enabled and the response does not reveal it as an available tool

#### Scenario: Auto-enable recovery ignores excluded tools
- **WHEN** the model emits a tool call for `delete_task_profile` triggering tool-not-found recovery
- **THEN** the recovery path does not enable the tool and the call fails as unknown
