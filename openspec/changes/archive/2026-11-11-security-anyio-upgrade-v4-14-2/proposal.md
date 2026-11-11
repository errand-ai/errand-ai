## Why

[Renovate PR #268](https://github.com/errand-ai/errand-ai/pull/268) upgrades AnyIO from 4.13.0 to 4.14.2 in the eval driver's test dependencies to address two reported vulnerabilities. Its critical TLS certificate-spoofing advisory and medium process-pool deadlock advisory justify prompt remediation, while the changed test-only pin does not establish production exposure.

## What Changes

- Adopt the PR's exact `anyio==4.14.2` pin in `evals/requirements-test.txt`; retain the other test pins and the lazy MCP import design.
- Verify installation and the eval unit suite using the same working directory as CI, without invoking live evals or modifying stored results.
- Resolve the PR's missing-`VERSION` review concern before merge: choose an unused patch release against current main, rather than relying on a green PR version check. PR builds use unique prerelease tags; main enforces immutable release tags.
- Keep this proposal unarchived until implementation and verification are complete; archive it in the implementing PR before merge, following repository conventions.

## Capabilities

### New Capabilities

None. This is test-tooling dependency maintenance, not a new product capability.

### Modified Capabilities

None. Existing `eval-driver` requirements (pure MCP client, sequential execution, profile lifecycle, yielding, resumability, retry, retro mode and configuration) remain unchanged. The change opts out of delta specs with `skip_specs: true` in `.openspec.yaml`; it must not invent product TLS or process-pool requirements for behavior supplied by an upstream test dependency.

## Impact

- Direct component: errand-ai's eval test environment and CI eval test step (`.github/workflows/build.yml`). Expected implementation files: `evals/requirements-test.txt`, `VERSION`, and this OpenSpec change/archive.
- No intended changes to errand backend, task-runner, frontend, Helm interfaces, databases, corpus or scoring, or errand-cloud. Runtime dependency remediation is separate work if an exposure audit establishes it.
- errand-website: no expected user-facing documentation change. After implementation verification, the Analyst reviews documentation impact and coordinates any needed release/security note through Team Leader to Website; no production vulnerability claim without evidence.

## Security Context and Evidence

The live PR was inspected at head `fcd8d45a189dd8a072904c34502bdd6d69843eb1`; its only changed file is `evals/requirements-test.txt`.

- [CVE-2026-63374 / GHSA-82r6-8w77-94w6](https://github.com/advisories/GHSA-82r6-8w77-94w6): PR reports CVSS 9.3. TLS connections to internationalized hostnames can match the wrong certificate under IDNA 2003 encoding when the connection is separately hijacked/redirected and the attacker presents a legitimate certificate for the mapped hostname. The PR reports an IDNA 2008 fix in 4.14.2.
- [CVE-2026-64847 / GHSA-5p39-cfhj-2xmp](https://github.com/advisories/GHSA-5p39-cfhj-2xmp): PR reports CVSS 6.8. Untrusted or faulty process-pool worker code can fill an undrained stderr pipe and deadlock the awaiting call. The PR reports stderr redirection to `os.devnull` in 4.14.2.
- [Review comment](https://github.com/errand-ai/errand-ai/pull/268#issuecomment-5739766935) flags the missing release-version bump. These advisory descriptions are sourced from the PR, not an independent proof that Errand executes vulnerable paths.

## Non-goals

Do not implement custom TLS validation, stderr workarounds or upstream regression suites, broaden production dependency pins, run live eval tasks, merge PR #268 automatically, or archive an unimplemented proposal.
