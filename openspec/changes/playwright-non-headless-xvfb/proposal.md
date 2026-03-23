## Why

Some websites detect and block headless browsers via navigator properties, canvas fingerprinting, and WebGL capability checks. Running Playwright in non-headless (headed) mode with Xvfb provides a real rendering pipeline that bypasses these detection mechanisms. The official `playwright/mcp` image already ships with Xvfb and X11 libraries — no custom image build is needed.

## What Changes

- Override the Playwright MCP container entrypoint to start Xvfb before the MCP server process
- Remove the `--headless` flag (the official image's entrypoint forces it; we replace the entrypoint entirely)
- Set `DISPLAY=:99` environment variable for the Xvfb virtual display
- Add shared memory configuration (`shm_size` / `emptyDir medium: Memory`) for Chrome stability in headed mode
- Bump Playwright memory limit from 512Mi to 768Mi to accommodate headed mode overhead (~100-150MB more)
- Apply changes across all deployment modes: Docker Compose (testing + deploy), Kubernetes (Helm), and errand-desktop (Swift container engine)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `playwright-mcp-image`: Browser mode changes from headless to non-headless (headed) with Xvfb virtual display. Entrypoint changes from image default to custom shell command. Shared memory requirements change.
- `playwright-standalone`: Deployment resource limits change (memory 512Mi → 768Mi). K8s deployment adds emptyDir volume for /dev/shm. Docker Compose services add shm_size.

## Impact

- **Deployment configs**: `testing/docker-compose.yml`, `deploy/docker-compose.yml`, `helm/errand/templates/playwright-deployment.yaml`, `helm/errand/values.yaml`
- **errand-desktop**: `Sources/ErrandDesktop/Container/ContainerEngine.swift` (command overrides for Docker and Apple runtimes)
- **Resource usage**: ~100-150MB more memory per Playwright pod, slight CPU increase for Xvfb
- **No API changes**: The MCP server interface remains identical; only the browser rendering mode changes
- **No image change**: Same official Microsoft image, just different entrypoint/args
