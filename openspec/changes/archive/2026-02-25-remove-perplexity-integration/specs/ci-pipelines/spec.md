## REMOVED Requirements

### Requirement: Build Perplexity MCP image
**Reason**: Perplexity integration removed; sidecar container no longer exists
**Migration**: No migration needed — the `perplexity-mcp/` directory and Dockerfile are deleted

#### Scenario: No Perplexity MCP build job
- **WHEN** the CI pipeline runs
- **THEN** no `build-perplexity-mcp` job exists

## MODIFIED Requirements

### Requirement: Helm job depends on image builds
The `helm` job SHALL depend on `build-errand` and `build-task-runner`. The Helm chart SHALL not be packaged until all images have been successfully built and pushed.

#### Scenario: All builds succeed
- **WHEN** `build-errand` and `build-task-runner` both succeed
- **THEN** the `helm` job runs and packages the chart

#### Scenario: Application build fails
- **WHEN** `build-errand` fails
- **THEN** the `helm` job does not run
