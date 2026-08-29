## MODIFIED Requirements

### Requirement: Dependency-update automation via Renovate

The repository's dependency-update automation SHALL be provided by Renovate. The update *policy* SHALL be configured centrally in the `errand-ai/.github` default-repo so it inherits to all repositories in the `errand-ai` GitHub organisation. Each repository MAY carry a minimal root `renovate.json` whose only role is to extend that central preset (`"extends": ["local>errand-ai/.github:renovate"]`); such a file SHALL NOT restate or override policy. The Renovate policy SHALL open a pull request for every update it proposes (patch, minor, and major) and SHALL NOT auto-merge any update; human review and merge are required for every PR. GitHub Dependabot `version-updates` for this repository SHALL be disabled via GitHub UI settings once Renovate is actively opening PRs. Dependabot `security-updates` MAY remain enabled initially and SHALL be evaluated for removal after Renovate's `vulnerabilityAlerts` behaviour has been observed to be adequate in operation.

#### Scenario: Renovate opens a PR for a patch-level dependency update
- **WHEN** a direct or transitive dependency pinned in `errand/requirements.txt`, `errand/requirements-test.txt`, `frontend/package.json`, or `frontend/package-lock.json` has a patch-level release available
- **THEN** Renovate opens a pull request against the default branch that updates the relevant manifest(s) and requires a human reviewer to merge

#### Scenario: Renovate opens a PR for a minor or major update
- **WHEN** a dependency has a minor or major release available
- **THEN** Renovate opens a pull request and does not auto-merge it, regardless of CI result

#### Scenario: Root config extends the central preset and nothing more
- **WHEN** a reviewer inspects `renovate.json` at the root of the `errand-ai/errand-ai` repository
- **THEN** it contains only a `$schema` key and an `extends` array naming `local>errand-ai/.github:renovate`, and declares no package rules, schedules, or other policy of its own

#### Scenario: Renovate policy is not duplicated in this repository
- **WHEN** a reviewer searches this repository for Renovate *policy* — package rules, grouping, schedules, or automerge settings — in `renovate.json`, `renovate.json5`, `.renovaterc`, or a `renovate` key in `package.json`
- **THEN** no such policy is present; the effective configuration is provided by the `errand-ai/.github` default-repo
- **AND** the root `renovate.json` that does exist is a pointer, not policy — it carries only `$schema` and `extends`

#### Scenario: Dependabot version-updates disabled
- **WHEN** a reviewer inspects this repository's GitHub Security & analysis settings
- **THEN** Dependabot version-updates is disabled (Dependabot security-updates MAY remain enabled pending the Renovate vulnerability-alerts evaluation)
