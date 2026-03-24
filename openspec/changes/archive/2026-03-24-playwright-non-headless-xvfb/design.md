## Context

Playwright MCP currently runs in headless mode via the official Microsoft image (`mcr.microsoft.com/playwright/mcp:latest`). The image's entrypoint is:

```
ENTRYPOINT ["node", "cli.js", "--headless", "--browser", "chromium", "--no-sandbox"]
```

The `--headless` flag is what forces headless mode. Without it, the CLI runs headed by default. The image already ships with Xvfb (`/usr/bin/Xvfb`) and X11 libraries pre-installed — no additional packages are needed.

The change affects four deployment contexts:
1. `testing/docker-compose.yml` — local development
2. `deploy/docker-compose.yml` — standalone deployment
3. `helm/errand/templates/playwright-deployment.yaml` — Kubernetes production
4. `errand-desktop` (`ContainerEngine.swift`) — macOS desktop app (Docker + Apple Containerization runtimes)

## Goals / Non-Goals

**Goals:**
- Run Playwright browser in non-headless (headed) mode using Xvfb as the virtual display
- Use the same official Microsoft image (no custom Dockerfile)
- Apply consistently across all deployment modes
- Ensure Chrome stability with proper shared memory configuration

**Non-Goals:**
- VNC/noVNC access for visual debugging (can be added later)
- Custom Playwright image builds or Dockerfile
- Changing the Playwright MCP protocol or API surface
- GPU acceleration (Xvfb uses software rendering, which is sufficient)

## Decisions

### Decision: Override entrypoint with shell command

Replace the image's default entrypoint with a shell command that starts Xvfb, waits for it, then execs the MCP server process.

**Pattern (all deployment modes):**
```sh
sh -c "Xvfb :99 -screen 0 1920x1080x24 -ac -nolisten tcp &
       sleep 1 &&
       DISPLAY=:99 exec node /app/cli.js --browser chromium --no-sandbox \
         --isolated --port <PORT> --host 0.0.0.0 --allowed-hosts '*'"
```

**Rationale:** This avoids building a custom image while keeping the Xvfb lifecycle tied to the container. The `exec` ensures the node process becomes PID 1 for proper signal handling. The `sleep 1` gives Xvfb time to initialise the display.

**Alternative considered:** Custom Dockerfile with a startup script — rejected because the official image already has Xvfb installed, making a wrapper image unnecessary complexity.

### Decision: Xvfb configuration

- **Display**: `:99` (standard convention, avoids conflicts)
- **Resolution**: `1920x1080x24` (standard HD, 24-bit colour)
- **Flags**: `-ac` (disable access control), `-nolisten tcp` (security: no remote X connections)

### Decision: Memory limit 768Mi

Headed mode uses approximately 100-150MB more than headless. Current limit of 512Mi is tight; 768Mi provides adequate headroom without over-provisioning.

### Decision: Shared memory for Chrome

Chrome/Chromium uses `/dev/shm` for inter-process communication. The default 64MB in containers causes crashes in headed mode.

- **Docker Compose**: `shm_size: '2gb'`
- **Kubernetes**: `emptyDir` volume with `medium: Memory` and `sizeLimit: 2Gi` mounted at `/dev/shm`
- **errand-desktop (Docker)**: `--shm-size=2g` flag
- **errand-desktop (Apple Containerization)**: No action needed (Apple runtime handles shared memory differently)

## Risks / Trade-offs

- **~20% more memory usage** → Mitigated by bumping limit from 512Mi to 768Mi
- **Xvfb startup race** → Mitigated by `sleep 1` before launching the MCP server; TCP health check on MCP port ensures readiness before task-runners connect
- **No visual debugging** → Acceptable for now; VNC can be layered on later if needed
- **Software rendering only** → Sufficient for anti-detection purposes; GPU acceleration not available in Xvfb but not needed

## Migration Plan

1. Update all deployment configs (docker-compose, Helm, errand-desktop)
2. Bump errand VERSION file
3. Deploy — Playwright pods will restart with new entrypoint
4. Rollback: revert to previous entrypoint (restore `--headless` flag) — no data migration needed
