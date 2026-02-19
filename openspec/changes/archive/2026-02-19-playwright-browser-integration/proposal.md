## Why

The task runner agent currently has no browser automation capability. Tasks that require interacting with web UIs (automated testing of frontends being developed by the agent) or browsing websites that block simple HTTP clients like curl are not possible. Adding Playwright browser control via the MCP protocol gives the agent full browser capabilities — navigation, clicking, form filling, screenshots, and JavaScript evaluation — without modifying the hardened distroless task-runner image.

## What Changes

- New `playwright-mcp` Docker image built from Microsoft's Playwright base with `@playwright/mcp` serving Streamable HTTP on port 8931
- Worker creates a Playwright MCP sidecar container in DinD alongside the task-runner for each task, both using `network_mode="host"` so they share the pod network namespace
- Worker manages the full lifecycle: start Playwright container, health-check readiness, inject MCP URL into task-runner config, run task-runner, tear down both containers
- Playwright container gets Docker-level memory limits so an OOM-kill only affects the browser, not the worker pod or in-flight task-runner
- Task-runner agent gains a `call_model_input_filter` that strips old screenshots from conversation history to prevent context window overflow during multi-turn runs with vision content
- CI pipeline builds and pushes the new `playwright-mcp` image alongside existing images
- Helm chart gains configuration values for the Playwright MCP image and container resource limits

## Capabilities

### New Capabilities
- `playwright-mcp-image`: Dockerfile and image build for the Playwright MCP server container (base image, `@playwright/mcp` install, port/host configuration, headless browser setup)
- `agent-context-management`: `call_model_input_filter` implementation in the task-runner that limits retained screenshots and large tool outputs to prevent context window overflow during long agent runs

### Modified Capabilities
- `task-worker`: Worker creates and manages a Playwright MCP sidecar container alongside the task-runner in DinD, with health-check, MCP URL injection, resource limits, and cleanup
- `helm-deployment`: New Helm values for `playwright-mcp` image (repository, tag) and DinD container resource limits; worker deployment template passes these as environment variables
- `ci-pipelines`: CI builds and pushes the `playwright-mcp` Docker image to GHCR alongside frontend, backend, and task-runner images

## Impact

- **New image**: `playwright-mcp` (~1-2GB due to Chromium) — separate from task-runner, does not affect its distroless security posture
- **Worker code**: `process_task_in_container()` in `backend/worker.py` gains container lifecycle management for the Playwright sidecar
- **Task-runner code**: `task-runner/main.py` gains a `RunConfig` with `call_model_input_filter` for context management
- **Helm chart**: `helm/content-manager/values.yaml` and `worker-deployment.yaml` gain Playwright image and resource limit configuration
- **CI**: `.github/workflows/build.yml` gains a build job for the Playwright MCP image
- **Resource usage**: Each worker pod now runs a headless Chromium process during task execution; memory-limited to prevent pod-level OOM
- **No breaking changes**: Playwright is additive — tasks that don't use browser tools are unaffected
