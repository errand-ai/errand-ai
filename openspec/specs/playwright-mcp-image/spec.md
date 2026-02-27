## Purpose

Playwright MCP server using the official Microsoft image for browser automation in task-runner containers.

## Requirements

### Requirement: Playwright MCP image

The worker SHALL use the official Microsoft Playwright MCP image (`mcr.microsoft.com/playwright/mcp`) to provide browser automation capabilities. No custom Dockerfile is required — the official image includes Chromium, the `@playwright/mcp` package, and supports Streamable HTTP transport natively via `--port`, `--host`, and `--allowed-hosts` CLI flags.

The worker SHALL start the Playwright MCP container with the command `--port 8931 --host 0.0.0.0 --allowed-hosts *` to enable Streamable HTTP on all interfaces and accept requests from any hostname.

#### Scenario: Streamable HTTP endpoint responds

- **WHEN** the Playwright MCP container starts with the configured command
- **THEN** the server listens on port 8931 and serves Streamable HTTP at `/mcp`

#### Scenario: Headless browser available

- **WHEN** a client connects to the MCP server and requests a browser action
- **THEN** the server launches headless Chromium and returns results without requiring a display server

#### Scenario: Requests accepted from any hostname

- **WHEN** a health check request is sent with a non-localhost Host header (e.g. `Host: dind:8931`)
- **THEN** the server accepts the request (due to `--allowed-hosts *`)
