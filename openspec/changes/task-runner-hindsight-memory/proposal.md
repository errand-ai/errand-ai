## Why

The task runner currently has no memory across executions — each task starts from scratch with no awareness of past tasks, decisions, or context. Integrating Hindsight gives the agent persistent memory so it can recall relevant information from previous executions (e.g. repository structure, user preferences, past decisions) and retain new learnings for future tasks.

## What Changes

- Add Hindsight as an MCP server available to the task runner agent, enabling it to `retain`, `recall`, and `reflect` during task execution
- Worker pre-loads relevant memories from Hindsight via REST API and injects them into the system prompt before each task execution
- Add Hindsight service to `docker-compose.yml` for local development
- Add `HINDSIGHT_URL` and `HINDSIGHT_BANK_ID` configuration to worker environment and admin settings
- Update Helm chart values with Hindsight connection settings for K8s deployment

## Capabilities

### New Capabilities
- `task-runner-memory`: Hindsight integration for persistent agent memory — MCP server injection, worker-level context pre-loading, memory bank configuration, and docker-compose service

### Modified Capabilities
- `task-worker`: Worker gains Hindsight REST API recall before launching the task runner, injects recalled context into the system prompt, and injects Hindsight MCP server into the task runner's MCP configuration
- `local-dev-environment`: Docker Compose gains a Hindsight service for local testing
- `task-runner-agent`: Task runner gains Hindsight MCP tools (retain, recall, reflect) and a system prompt section instructing the agent how to use its memory

## Impact

- **task-runner/**: New `hindsight-client` dependency in requirements.txt (not strictly needed if MCP-only, but useful for worker-level pre-loading)
- **backend/worker.py**: New Hindsight recall + MCP injection logic in `process_task_in_container`
- **backend/main.py**: New admin settings fields (`hindsight_url`, `hindsight_bank_id`)
- **docker-compose.yml**: New `hindsight` service
- **helm/content-manager/**: New values for Hindsight URL and bank ID, new environment variables on worker deployment
- **Dependencies**: `hindsight-client` Python package added to backend requirements (for worker-level recall)
