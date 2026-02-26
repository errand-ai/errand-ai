## Why

Users and administrators have no visibility into which version of the application is currently deployed, nor any indication when a newer version is available. This makes it easy to run outdated versions without realising it.

## What Changes

- Bake the application version (from CI) into the Docker image via a build arg / env var
- Add a backend `/api/version` endpoint that returns the current deployed version and the latest available release version
- Add a background task that periodically (every 15 minutes) queries the GHCR OCI tags API to discover the latest release tag
- Display the current version in the frontend header (next to the GitHub link) with a visual indicator when a newer version is available
- Update CI to pass the computed version tag (including `-prN` suffix for PR builds) as a Docker build arg

## Capabilities

### New Capabilities
- `version-api`: Backend endpoint and background checker that exposes current deployed version and latest available release from GHCR
- `version-display`: Frontend header element showing current version with update-available indicator

### Modified Capabilities
- `ci-pipelines`: CI must pass the version tag as a Docker build arg so it gets baked into the image

## Impact

- **Dockerfile**: New `ARG`/`ENV` for `APP_VERSION`
- **CI workflow** (`build.yml`): Add `--build-arg APP_VERSION` to Docker build steps
- **Backend** (`errand/`): New `version_checker.py` module, new `/api/version` endpoint, new background task in lifespan
- **Frontend** (`frontend/src/`): Version display in `App.vue` header, periodic fetch of `/api/version`
- **docker-compose**: Optionally pass `APP_VERSION` for local dev
- **External dependency**: Anonymous GHCR OCI registry API (public, no credentials needed)
