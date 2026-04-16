## ADDED Requirements

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
