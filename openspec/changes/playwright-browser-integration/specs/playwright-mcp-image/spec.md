## ADDED Requirements

### Requirement: Playwright MCP Dockerfile

The repository SHALL include a `playwright-mcp/Dockerfile` that produces a container image capable of serving the Playwright MCP server over Streamable HTTP. The Dockerfile SHALL use `mcr.microsoft.com/playwright:v1.50.0-noble` as the base image. The image SHALL install `@playwright/mcp` globally via npm. The image SHALL expose port 8931. The default command SHALL run `npx @playwright/mcp --port 8931 --host 0.0.0.0`. The container SHALL run headless Chromium — no display server is required.

#### Scenario: Image builds successfully

- **WHEN** `docker build -t playwright-mcp playwright-mcp/` is run
- **THEN** the image builds without errors and is tagged `playwright-mcp`

#### Scenario: MCP server starts and listens

- **WHEN** the container starts with default command
- **THEN** the Playwright MCP server listens on port 8931 and serves Streamable HTTP at `/mcp`

#### Scenario: Headless browser available

- **WHEN** a client connects to the MCP server and requests a browser snapshot
- **THEN** the server launches headless Chromium and returns results without requiring a display server

### Requirement: Playwright MCP server serves Streamable HTTP transport

The Playwright MCP server SHALL serve the Streamable HTTP transport at the `/mcp` path and the legacy SSE transport at the `/sse` path on the same port. The task-runner SHALL connect using the Streamable HTTP transport at `http://localhost:8931/mcp`.

#### Scenario: Streamable HTTP endpoint responds

- **WHEN** an MCP client sends a POST request to `http://localhost:8931/mcp`
- **THEN** the server responds with a valid MCP Streamable HTTP response

#### Scenario: SSE endpoint available as fallback

- **WHEN** an MCP client connects to `http://localhost:8931/sse`
- **THEN** the server responds with a valid SSE stream
