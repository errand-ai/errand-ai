## MODIFIED Requirements

### Requirement: Playwright MCP image

The worker SHALL use the official Microsoft Playwright MCP image (`mcr.microsoft.com/playwright/mcp`) to provide browser automation capabilities. No custom Dockerfile is required — the official image includes Chromium, the `@playwright/mcp` package, Xvfb, X11 libraries, and supports Streamable HTTP transport natively via `--port`, `--host`, and `--allowed-hosts` CLI flags.

The container entrypoint SHALL be overridden to start Xvfb before the MCP server process. The entrypoint SHALL:
1. Start `Xvfb :99 -screen 0 1920x1080x24 -ac -nolisten tcp` as a background process
2. Wait for Xvfb to initialise (minimum 1 second delay)
3. Set `DISPLAY=:99` and exec `node /app/cli.js --browser chromium --no-sandbox --isolated --port <PORT> --host 0.0.0.0 --allowed-hosts *`

The `--headless` flag SHALL NOT be used. The MCP server SHALL run in headed (non-headless) mode, rendering to the Xvfb virtual display.

The container SHALL have shared memory (`/dev/shm`) sized to at least 2GB to support Chrome inter-process communication in headed mode.

#### Scenario: Streamable HTTP endpoint responds

- **WHEN** the Playwright MCP container starts with the Xvfb entrypoint override
- **THEN** the server listens on the configured port and serves Streamable HTTP at `/mcp`

#### Scenario: Non-headless browser with Xvfb

- **WHEN** a client connects to the MCP server and requests a browser action
- **THEN** the server launches non-headless Chromium rendering to the Xvfb virtual display at `:99`

#### Scenario: Requests accepted from any hostname

- **WHEN** a health check request is sent with a non-localhost Host header (e.g. `Host: dind:8931`)
- **THEN** the server accepts the request (due to `--allowed-hosts *`)
