## ADDED Requirements

### Requirement: Build Perplexity MCP image
The CI workflow SHALL include a `build-perplexity-mcp` job that builds the Docker image from `perplexity-mcp/Dockerfile` and pushes it to the container registry. The job SHALL depend on the `version` job. The image SHALL be tagged with the version from the `VERSION` file (same as other images). On pull requests, the image SHALL be tagged with the PR-specific tag (e.g., `0.4.0-pr5`). The `helm` job SHALL depend on `build-perplexity-mcp` in addition to the existing build jobs.

#### Scenario: Perplexity MCP image built on main push
- **WHEN** a commit is pushed to `main` and `VERSION` contains `0.5.0`
- **THEN** the Perplexity MCP image is built and pushed with tag `0.5.0`

#### Scenario: Perplexity MCP image built on PR
- **WHEN** PR #5 is created and `VERSION` contains `0.5.0`
- **THEN** the Perplexity MCP image is built and pushed with tag `0.5.0-pr5`

#### Scenario: Helm job waits for Perplexity MCP build
- **WHEN** the CI pipeline runs
- **THEN** the `helm` job depends on `build-perplexity-mcp` completing successfully
