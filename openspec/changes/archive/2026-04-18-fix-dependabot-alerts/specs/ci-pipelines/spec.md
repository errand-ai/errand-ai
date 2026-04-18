## ADDED Requirements

### Requirement: Dependency-update automation via Renovate

The repository's dependency-update automation SHALL be provided by Renovate, configured centrally in the `errand-ai/.github` default-repo so the policy inherits to all repositories in the `errand-ai` GitHub organisation without per-repo configuration files. The Renovate policy SHALL open a pull request for every update it proposes (patch, minor, and major) and SHALL NOT auto-merge any update; human review and merge are required for every PR. GitHub Dependabot `version-updates` for this repository SHALL be disabled via GitHub UI settings once Renovate is actively opening PRs. Dependabot `security-updates` MAY remain enabled initially and SHALL be evaluated for removal after Renovate's `vulnerabilityAlerts` behaviour has been observed to be adequate in operation.

#### Scenario: Renovate opens a PR for a patch-level dependency update
- **WHEN** a direct or transitive dependency pinned in `errand/requirements.txt`, `errand/requirements-test.txt`, `frontend/package.json`, or `frontend/package-lock.json` has a patch-level release available
- **THEN** Renovate opens a pull request against the default branch that updates the relevant manifest(s) and requires a human reviewer to merge

#### Scenario: Renovate opens a PR for a minor or major update
- **WHEN** a dependency has a minor or major release available
- **THEN** Renovate opens a pull request and does not auto-merge it, regardless of CI result

#### Scenario: Renovate config is not in this repository
- **WHEN** a reviewer searches for a `renovate.json`, `renovate.json5`, `.renovaterc`, or `renovate` key in `package.json` in the `errand-ai/errand-ai` repository
- **THEN** no such file or key is present; the effective configuration is provided by the `errand-ai/.github` default-repo

#### Scenario: Dependabot version-updates disabled
- **WHEN** a reviewer inspects this repository's GitHub Security & analysis settings
- **THEN** Dependabot version-updates is disabled (Dependabot security-updates MAY remain enabled pending the Renovate vulnerability-alerts evaluation)
