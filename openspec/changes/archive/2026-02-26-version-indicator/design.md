## Context

The application currently has no mechanism to communicate its deployed version to users or to detect when a newer release is available. The VERSION file drives CI tagging but the version is not baked into the Docker image or exposed at runtime. The GHCR container registry at `ghcr.io/errand-ai/errand` is public, so tag enumeration requires no credentials (only an anonymous OCI token exchange).

## Goals / Non-Goals

**Goals:**
- Display the deployed version in the frontend header for all users
- Detect newer release versions from GHCR and indicate availability in the UI
- Support both release tags (`0.65.0`) and PR pre-release tags (`0.65.0-pr66`)

**Non-Goals:**
- Triggering or managing upgrades (deployment methodology varies)
- Changelog display or release notes
- Version checking for the task-runner image (only the main errand image)

## Decisions

### 1. Version injection via Docker build arg

The Dockerfile gets `ARG APP_VERSION="dev"` and `ENV APP_VERSION=$APP_VERSION`. CI passes `--build-arg APP_VERSION=<tag>` in the Docker build step. The backend reads `os.environ.get("APP_VERSION", "dev")` at startup.

**Alternatives considered:**
- Copying the VERSION file into the image and reading at runtime — doesn't handle the `-prN` suffix that CI appends for PR builds
- Vite build-time injection (`import.meta.env.VITE_APP_VERSION`) — would work for display but the backend needs the version anyway for the comparison logic, and having a single source (the backend endpoint) is cleaner

### 2. Backend `/api/version` endpoint + background checker

A new `version_checker.py` module handles:
- Storing the current version from `APP_VERSION` env var
- Running a background async loop (check on startup, then every 15 minutes) that queries GHCR
- Caching the latest release version and update-available flag
- Exposing state via a simple function called by the endpoint

The endpoint `GET /api/version` returns:
```json
{
  "current": "0.65.0",
  "latest": "0.66.0",
  "update_available": true
}
```

When the GHCR check hasn't completed yet or has failed, `latest` is `null` and `update_available` is `false`.

**Rationale:** Follows the existing pattern of standalone background tasks (`run_scheduler`, `run_zombie_cleanup`, `run_status_updater`) launched via `asyncio.create_task()` in the lifespan. The backend already has `httpx` available for async HTTP.

### 3. GHCR OCI tags API with anonymous token

The check flow:
1. `GET https://ghcr.io/token?scope=repository:errand-ai/errand:pull` — returns anonymous bearer token
2. `GET https://ghcr.io/v2/errand-ai/errand/tags/list` with bearer token — returns `{"tags": [...]}`
3. Filter out tags matching the pattern `-pr\d+$` (PR pre-release builds)
4. Parse remaining tags as semver, find the maximum
5. Compare against the current version's base (strip any `-prN` suffix)

The GHCR image path (`errand-ai/errand`) is hardcoded as a constant. This is a single-product app, not a framework.

### 4. Version comparison logic

```
current_base = strip "-prN" suffix from APP_VERSION
update_available = latest_release > current_base (semver comparison)
```

Examples:
- Current `0.65.0`, latest release `0.66.0` → update available
- Current `0.65.0-pr66`, latest release `0.65.0` → no update (same base)
- Current `0.65.0-pr66`, latest release `0.66.0` → update available
- Current `dev`, latest release `0.66.0` → no update (dev can't be compared)

Python's `packaging.version.Version` handles semver parsing. It's already in the dependency tree (transitive via pip/setuptools).

### 5. Frontend display

The version is shown in the header, right-aligned, between the nav links and the GitHub icon:

```
[Logo] [Nav...]          v0.65.0  [GitHub ↗]  [User ▾]
```

When an update is available, a small colored dot appears after the version text with a tooltip showing the latest version:

```
[Logo] [Nav...]          v0.65.0 ●  [GitHub ↗]  [User ▾]
                                 ↑
                          tooltip: "v0.66.0 available"
```

The frontend fetches `/api/version` on mount. It does not need its own polling interval — the backend caches the GHCR result, so the frontend gets a fresh answer whenever the page loads or the user navigates.

### 6. docker-compose for local dev

docker-compose can pass `APP_VERSION` from the VERSION file using an env var or build arg. In local dev the version will show as `dev` unless explicitly configured — this is fine, local dev doesn't need update checking.

## Risks / Trade-offs

- **GHCR rate limiting** → 15-minute interval is conservative; anonymous token requests are lightweight. If GHCR is unreachable, the checker logs a warning and retries next interval. The endpoint returns `latest: null, update_available: false` during failures.
- **Hardcoded GHCR path** → Acceptable for this single-product app. If the org/repo ever changes, it's a one-line constant update.
- **`packaging` dependency** → Already transitively available. If it ever disappears, `re`-based semver parsing is trivial as a fallback.
