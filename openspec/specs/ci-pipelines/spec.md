## Purpose

GitHub Actions CI pipeline with multi-stage Docker builds, Helm chart packaging, and version tagging for PRs and main.

## Requirements

### Requirement: Multi-stage Docker builds
The CI pipeline SHALL use a multi-stage Dockerfile for the application image: a Node.js stage to build the frontend assets, a Python build stage to install dependencies, and a slim Python runtime as the final stage. The Dockerfile SHALL copy source from `errand/` (not `backend/`). The task runner SHALL continue to use its own Dockerfile. The Dockerfile SHALL accept an `APP_VERSION` build argument and set it as an environment variable in the final image. CI SHALL pass the computed version tag (including `-prN` suffix for PR builds) as `--build-arg APP_VERSION=<tag>` when building the application image.

#### Scenario: Application image build
- **WHEN** the application Docker image is built
- **THEN** the final image contains the Python runtime, installed dependencies from `errand/requirements.txt`, application code from `errand/`, and the frontend static assets in a `static/` directory — but not Node.js, npm, or frontend source files

#### Scenario: Version baked into image
- **WHEN** the CI builds the application image with tag `0.65.0`
- **THEN** the Docker build receives `--build-arg APP_VERSION=0.65.0` and the running container has `APP_VERSION=0.65.0` in its environment

#### Scenario: PR version baked into image
- **WHEN** the CI builds a PR image with tag `0.65.0-pr66`
- **THEN** the Docker build receives `--build-arg APP_VERSION=0.65.0-pr66` and the running container has `APP_VERSION=0.65.0-pr66` in its environment

### Requirement: Least-privilege GITHUB_TOKEN permissions
The GitHub Actions build workflow (`.github/workflows/build.yml`) SHALL declare an explicit top-level `permissions:` block that defaults to the minimum required scope (`contents: read`). Individual jobs SHALL override the default only to widen specific scopes they genuinely require (for example, `packages: write` for jobs that push images to GHCR, `id-token: write` for jobs that perform OIDC exchanges, `contents: write` for jobs that push tags or branches). No job SHALL rely on implicit repository-default permissions for write access. No existing job's effective permissions SHALL be weakened by this change.

#### Scenario: Workflow declares top-level permissions
- **WHEN** `.github/workflows/build.yml` is inspected
- **THEN** it SHALL contain a top-level `permissions:` block set to `contents: read` (at minimum)

#### Scenario: Write access is explicit
- **WHEN** any job in the workflow pushes to GHCR, tags the repository, exchanges an OIDC token, or otherwise requires write access beyond `contents: read`
- **THEN** that job SHALL declare its own `permissions:` block granting only the additional scopes it needs (e.g., `packages: write`, `id-token: write`, `contents: write`)

#### Scenario: Existing permissions preserved
- **WHEN** comparing the workflow before and after this change
- **THEN** every job that previously had write access SHALL continue to have at least those same write scopes after the change

#### Scenario: CodeQL workflow-permissions alert closed
- **WHEN** CodeQL scans the workflow after this change
- **THEN** the `actions/missing-workflow-permissions` alert SHALL no longer be raised
