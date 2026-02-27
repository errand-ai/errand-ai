## Purpose

Backend endpoint returning current deployed version, latest available release, and update availability.

## Requirements

### Requirement: Version endpoint returns current and latest version
The backend SHALL expose a `GET /api/version` endpoint that returns the current deployed version, the latest available release version, and whether an update is available. The endpoint SHALL NOT require authentication.

#### Scenario: Normal response with no update
- **WHEN** the deployed version is `0.65.0` and the latest GHCR release tag is `0.65.0`
- **THEN** the endpoint returns `{"current": "0.65.0", "latest": "0.65.0", "update_available": false}`

#### Scenario: Update available
- **WHEN** the deployed version is `0.65.0` and the latest GHCR release tag is `0.66.0`
- **THEN** the endpoint returns `{"current": "0.65.0", "latest": "0.66.0", "update_available": true}`

#### Scenario: PR build with matching release
- **WHEN** the deployed version is `0.65.0-pr66` and the latest GHCR release tag is `0.65.0`
- **THEN** the endpoint returns `{"current": "0.65.0-pr66", "latest": "0.65.0", "update_available": false}`

#### Scenario: PR build with newer release available
- **WHEN** the deployed version is `0.65.0-pr66` and the latest GHCR release tag is `0.66.0`
- **THEN** the endpoint returns `{"current": "0.65.0-pr66", "latest": "0.66.0", "update_available": true}`

#### Scenario: GHCR check not yet completed
- **WHEN** the background checker has not completed its first check or the last check failed
- **THEN** the endpoint returns `{"current": "<version>", "latest": null, "update_available": false}`

#### Scenario: Dev version
- **WHEN** the deployed version is `dev` (no APP_VERSION set)
- **THEN** the endpoint returns `{"current": "dev", "latest": null, "update_available": false}`

### Requirement: Current version read from environment
The backend SHALL read the current version from the `APP_VERSION` environment variable at startup. If the variable is not set, the version SHALL default to `"dev"`.

#### Scenario: APP_VERSION set
- **WHEN** `APP_VERSION` is set to `0.65.0`
- **THEN** the current version reported by the endpoint is `0.65.0`

#### Scenario: APP_VERSION not set
- **WHEN** `APP_VERSION` is not set
- **THEN** the current version reported by the endpoint is `dev`

### Requirement: Background GHCR tag checker
The backend SHALL run a background task that queries the GHCR OCI registry for available tags of the `errand-ai/errand` image. The check SHALL run once on startup and then every 15 minutes. The checker SHALL use anonymous authentication (OCI token exchange with no credentials).

#### Scenario: Periodic check interval
- **WHEN** the application starts
- **THEN** the checker runs immediately and then repeats every 15 minutes

#### Scenario: GHCR unreachable
- **WHEN** the GHCR API is unreachable or returns an error
- **THEN** the checker logs a warning and retries at the next interval; the cached latest version remains unchanged (or null if no successful check has occurred)

### Requirement: Pre-release tag filtering
The GHCR tag checker SHALL filter out tags matching the pattern `-pr\d+$` (PR pre-release builds) when determining the latest release version. Only clean semver tags SHALL be considered as release versions.

#### Scenario: Mixed tags in registry
- **WHEN** the registry contains tags `0.64.0`, `0.65.0`, `0.65.0-pr66`, `0.66.0-pr67`
- **THEN** the latest release version is `0.65.0`

#### Scenario: Only pre-release tags
- **WHEN** the registry contains only tags matching `-pr\d+$`
- **THEN** the latest release version is `null`

### Requirement: Semver comparison for update detection
The checker SHALL compare the latest release version against the current version's base (with any `-prN` suffix stripped) using semantic versioning. An update is available only when the latest release is strictly greater than the current base version.

#### Scenario: Current version has pre-release suffix
- **WHEN** the current version is `0.65.0-pr66`
- **THEN** the base version for comparison is `0.65.0`

#### Scenario: Latest equals current base
- **WHEN** the current base version is `0.65.0` and latest release is `0.65.0`
- **THEN** update_available is `false`

#### Scenario: Latest greater than current base
- **WHEN** the current base version is `0.65.0` and latest release is `0.66.0`
- **THEN** update_available is `true`
