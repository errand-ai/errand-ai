## Context

The content-manager is deployed to Kubernetes for production use, and uses docker-compose for local development. A third deployment target — a native macOS desktop application — would make the application accessible to users who don't have Docker or Kubernetes knowledge.

Apple's Containerization framework (macOS 26+, Apple silicon) provides Swift APIs for running OCI containers as lightweight VMs, eliminating the need for Docker Desktop. The `worker-container-runtime-abstraction` change introduces a pluggable `ContainerRuntime` interface that this app extends with an `AppleContainerRuntime`.

## Goals / Non-Goals

**Goals:**
- Native macOS menu bar app that manages the full content-manager stack
- One-click start/stop for all services
- Service health monitoring with status indicators
- Open the frontend in the default browser
- Optional LiteLLM service for multi-provider LLM management
- Persistent local storage for PostgreSQL and Valkey
- Distributable as a signed, notarized DMG

**Non-Goals:**
- iOS or iPadOS support
- App Store distribution (use Developer ID / direct distribution)
- Replicating the Helm chart or K8s deployment logic
- Building container images locally (app pulls pre-built images from GHCR)
- Supporting Intel Macs or macOS versions before 26

## Decisions

### Decision 1: Separate repository for the macOS app

**Choice**: The macOS app lives in its own repository (e.g., `content-manager-desktop`) as a Swift Package / Xcode project. It references content-manager container images by tag but has its own versioning and release cycle.

**Why**: The Swift toolchain (Xcode, SPM) is fundamentally different from the Python/Node toolchain. Mixing them in one repo adds complexity for CI, contributors, and IDE support. The app is a consumer of content-manager images, not part of the same build pipeline.

### Decision 2: Containerization.framework for container management

**Choice**: Use Apple's Containerization Swift package directly (not the `container` CLI) for all container lifecycle operations: pulling images, creating containers, binding volumes, managing networking, and monitoring health.

**Why**: The Swift API integrates naturally with the SwiftUI app, provides programmatic control over all container operations, and avoids the overhead of shelling out to a CLI. The framework is the same foundation the `container` CLI is built on.

### Decision 3: Bridge API for worker → task-runner container creation

**Choice**: The Swift app exposes a local HTTP API (e.g., on a Unix domain socket or localhost port) that the worker container uses to request task-runner container creation. The API accepts the image, env vars, and files, and the Swift app creates the Apple Container. The worker polls for status and retrieves output.

**Endpoints:**
- `POST /containers` — create and start a task-runner container
- `GET /containers/{id}/logs` — stream container logs (SSE)
- `GET /containers/{id}/status` — get container status and exit code
- `GET /containers/{id}/output` — read `/output/result.json` from the container
- `DELETE /containers/{id}` — remove the container

**Why**: The worker runs inside an Apple Container VM and cannot directly invoke the Containerization framework on the host. The bridge API solves this by letting the host app manage all containers centrally. This is analogous to how the Docker daemon exposes an API.

### Decision 4: Inter-container networking via host-managed IPs

**Choice**: The Swift app assigns each container a dedicated IP (Apple Container's default networking model). It passes service URLs as environment variables to containers that need to reach other services (e.g., `DATABASE_URL=postgresql://...:5432/...`, `VALKEY_URL=redis://...:6379`).

**Why**: Apple Container doesn't have Docker-style named networks or DNS. The host app knows each container's IP and can inject connection strings at startup.

### Decision 5: LiteLLM as an optional service

**Choice**: The settings UI includes a toggle for LiteLLM. When enabled, the app runs a LiteLLM container (e.g., `ghcr.io/berriai/litellm:latest`) and configures the backend and worker to use it as their `OPENAI_BASE_URL`. The LiteLLM config file is stored locally and editable through the app.

**Why**: LiteLLM provides a unified OpenAI-compatible proxy for multiple LLM providers (OpenAI, Anthropic, local Ollama, etc.). Making it optional keeps the app simple for users who only need one provider, while offering power users a multi-provider setup.

### Decision 6: Persistent storage in Application Support

**Choice**: Container data volumes are bind-mounted from `~/Library/Application Support/ContentManager/data/`:
- `postgres/` — PostgreSQL data directory
- `valkey/` — Valkey persistence (RDB/AOF)
- `litellm/` — LiteLLM config (if enabled)
- `config.json` — App settings (enabled services, LLM keys, ports)

**Why**: `~/Library/Application Support/` is the standard macOS location for application data. It persists across app updates, is included in Time Machine backups, and follows Apple's filesystem guidelines.

### Decision 7: MenuBarExtra with popover UI

**Choice**: SwiftUI `MenuBarExtra` with a popover (not a dropdown menu) showing:
- Service status list (name, status indicator, port)
- Start All / Stop All buttons
- Open in Browser button
- Settings gear icon (opens a settings window)
- Logs button (opens a log viewer window)

**Why**: A popover provides richer UI than a menu — status indicators, buttons, and layout — while staying lightweight. Settings and logs open as separate windows for more space.

### Decision 8: Auto-update mechanism

**Choice**: The app checks for new versions on startup (and periodically) by querying GitHub releases for both the app itself and the content-manager container images. When updates are available, the app shows a notification and offers to pull new images / download the new app version.

**Why**: Users of a desktop app expect automatic update notifications. Since this is distributed outside the App Store, Sparkle (the standard macOS update framework) or a custom GitHub-based updater can handle this.

## Risks / Trade-offs

**[Containerization framework maturity]** → Apple Container is pre-1.0 (v0.9.0 as of Feb 2026). Minor version updates may include breaking changes. Mitigation: pin to a specific framework version; test against updates before releasing.

**[macOS 26 requirement]** → Only users on macOS 26+ with Apple silicon can use the app. Mitigation: acceptable for the target audience (developers and power users typically run recent macOS).

**[Bridge API security]** → The local HTTP API for the worker to request containers must not be accessible from outside the host. Mitigation: bind to localhost only, or use a Unix domain socket. Add a shared secret token generated at startup.

**[Apple Developer Program cost]** → $99/year for code signing and notarization. Mitigation: required for any distributed macOS app; cost is minimal.

**[Container image size]** → First launch requires pulling several OCI images (backend, worker, task-runner, postgres, valkey, optionally litellm). This could be slow on initial setup. Mitigation: show progress UI during first-run image pull; cache images locally.

## Open Questions

- Should the Playwright container also be managed by the Swift app, or run as a sidecar inside the worker container? (Leaning toward the Swift app managing it for consistency.)
- What's the best auto-update framework for macOS apps distributed outside the App Store? (Sparkle is the standard.)
