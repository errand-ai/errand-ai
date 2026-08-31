## Why

`task-runner/Dockerfile:79` runs an unauthenticated `git clone` of
`googleworkspace/cli` solely to copy `skills/gws-*` out of the tag. Every
task-runner build depends on it, once per architecture, and it is the only
unauthenticated git operation in any build.

On 2026-08-31 it failed four consecutive builds on PR #251 with
`fatal: could not read Username for 'https://github.com'` on the `linux/arm64`
QEMU leg, blocking the `helm` job and the PR for roughly four hours, then
succeeded untouched. The `curl` of the release tarball earlier in the *same
stage* succeeded throughout, so the fault is specific to the unauthenticated git
protocol rather than to GitHub reachability. Nothing about the repo, the tag, or
the Dockerfile changed across the failures.

## What Changes

- Replace the unauthenticated `git clone` in the `gws-builder` stage with a
  fetch that does not depend on anonymous git. The mechanism is a design
  decision (authenticate the clone with the `GITHUB_TOKEN` the build job already
  holds; `curl` the source archive, matching how the `gws` binary is already
  fetched; or vendor the skills into the repo) — this proposal fixes the
  requirement, not the implementation.
- The skills SHALL continue to be sourced at the tag named by `GWS_VERSION`, so
  the binary and its skills cannot drift apart.
- The fetched skills SHALL be integrity-verified, or their provenance be
  reviewable in-tree. Today the binary is checksum-verified against a published
  `.sha256` while the skills beside it are not verified at all.
- A local `docker build` with no credentials SHALL keep working, so the change
  does not move a CI-only failure onto contributors.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-runner-image`: the `gws-builder` stage requirement currently mandates
  "clone the repository at the matching version tag to obtain the bundled agent
  skills". That prescribes the failing mechanism, so the requirement is restated
  in terms of the outcome (skills sourced at the pinned version, verified) rather
  than the transport.

## Impact

- `task-runner/Dockerfile` — the `gws-builder` stage.
- `.github/workflows/build.yml` — only if the chosen mechanism needs a build
  secret; the `npm_token` secret plumbing in the root `Dockerfile` is the
  existing pattern to copy.
- Possibly `ci-pipelines` and vendored files in-tree, depending on the mechanism
  design settles on. If skills are vendored, a drift check against `GWS_VERSION`
  is required or the two silently diverge on the next version bump.
- No runtime behaviour change: the final image contains the same
  `/opt/system-skills/gws/` content either way. This is a build-reliability and
  supply-chain change only.
- Renovate currently has no view of `GWS_VERSION`; whichever mechanism is chosen
  should not make version bumps harder to automate later.
