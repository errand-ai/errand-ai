## Purpose

Standalone Playwright MCP deployment with `--isolated` mode for concurrent multi-session support, replacing the per-worker sidecar pattern.

## ADDED Requirements

### Requirement: Playwright runs with --isolated flag

The Playwright MCP server SHALL be started with the `--isolated` flag in all deployment modes (K8s and Docker Compose). This enables shared browser mode where each Streamable HTTP session gets its own isolated `BrowserContext` with separate cookies, localStorage, and navigation state. The persistent profile mode (default without `--isolated`) SHALL NOT be used.

#### Scenario: Two concurrent task-runners connect

- **WHEN** two task-runner containers connect to the same Playwright MCP instance simultaneously
- **THEN** each gets its own `BrowserContext` with fully isolated browser state

#### Scenario: Sessions do not interfere

- **WHEN** task-runner A navigates to page X and task-runner B navigates to page Y on the same Playwright instance
- **THEN** each task-runner sees only its own page; navigation and cookies are isolated

### Requirement: Standalone Playwright K8s Deployment

The Helm chart SHALL deploy Playwright MCP as a separate Deployment and Service (not a sidecar). The Deployment SHALL use the existing `playwright.image` values. The Service SHALL expose the Playwright port for internal cluster access. The Deployment args SHALL include `--isolated`, `--port`, `--host 0.0.0.0`, and `--allowed-hosts *`.

#### Scenario: Playwright accessible via service DNS

- **WHEN** a task-runner Job is created by the TaskManager
- **THEN** the task-runner connects to Playwright via the K8s Service DNS (e.g. `http://errand-playwright:3000`)

#### Scenario: Playwright pod restarts independently

- **WHEN** the Playwright pod crashes
- **THEN** K8s restarts it without affecting the server pods

### Requirement: Standalone Playwright in Docker Compose

The docker-compose configuration SHALL include a standalone Playwright service with `--isolated` flag on the `errand-net` named network. The errand service SHALL reference the Playwright service by Docker Compose DNS name. Task-runner containers, attached to the same named network via `TASK_RUNNER_NETWORK`, SHALL resolve the Playwright service by name.

#### Scenario: Playwright available in local dev

- **WHEN** a developer runs `docker compose up`
- **THEN** Playwright starts as a standalone service and task-runners connect to it via Compose DNS

### Requirement: Task-runner Playwright URL from environment

The TaskManager SHALL pass the Playwright MCP URL to task-runner containers via the `PLAYWRIGHT_MCP_URL` environment variable (or equivalent MCP config injection). The URL SHALL be derived from: (1) K8s Service DNS in production, (2) Docker Compose service DNS in local dev. The `POD_IP`-based Playwright URL construction SHALL be removed.

#### Scenario: K8s task-runner receives Playwright URL

- **WHEN** the TaskManager creates a K8s Job for a task and Playwright is enabled
- **THEN** the Playwright MCP entry in `mcp.json` uses the K8s Service URL

#### Scenario: Playwright not configured

- **WHEN** the Playwright Deployment is not enabled in Helm values
- **THEN** no Playwright MCP entry is injected into `mcp.json`
