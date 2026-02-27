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
