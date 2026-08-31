## Why

Two Dockerfiles run an unauthenticated `git clone` of `googleworkspace/cli`
solely to copy `skills/gws-*` out of the tag: `task-runner/Dockerfile:79`, once
per architecture on every task-runner build, and `Dockerfile:18`, which feeds
`/app/system-skills/gws/` in the server image. Both `build-task-runner` and
`build-errand` are required jobs, so either can block every PR.

On 2026-08-31 it failed four consecutive builds on PR #251 with
`fatal: could not read Username for 'https://github.com'` on the `linux/arm64`
QEMU leg, blocking the `helm` job and the PR for roughly four hours, then
succeeded untouched. The `curl` of the release tarball earlier in the *same
stage* succeeded throughout, so the fault is specific to the unauthenticated git
protocol rather than to GitHub reachability. Nothing about the repo, the tag, or
the Dockerfile changed across the failures. `build-errand` happened not to be
hit, but carries the identical exposure.

## What Changes

- Replace the unauthenticated `git clone` in **both** the task-runner
  `gws-builder` stage and the server image's `gws-skills` stage with a fetch
  that does not depend on anonymous git. The mechanism is a design decision
  (authenticate the clone with the `GITHUB_TOKEN` the build job already holds;
  `curl` the source archive, matching how the `gws` binary is already fetched;
  or vendor the skills into the repo) — this proposal fixes the requirement, not
  the implementation.
- Both images SHALL use the same mechanism, so the two cannot drift and a future
  reader does not have to work out why they differ.
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
- `google-workspace-integration`: two requirements describe the same mechanism
  and would otherwise contradict the above. "gws CLI installed in task-runner
  image" also says the skills are "cloned at the matching version tag"; "gws
  skills bundled in server image" permits any generation step and so does not
  currently forbid the clone this change removes.

## Impact

- `task-runner/Dockerfile` — the `gws-builder` stage.
- `Dockerfile` (repo root) — the `gws-skills` stage feeding the server image.
- `.github/workflows/build.yml` — only if the chosen mechanism needs a build
  secret; `build-errand` already passes `npm_token`, so that plumbing is the
  pattern to copy and the job needs only an additional entry.
- Possibly `ci-pipelines` and vendored files in-tree, depending on the mechanism
  design settles on. If skills are vendored, a drift check against `GWS_VERSION`
  is required or the two silently diverge on the next version bump.
- No runtime behaviour change: the final image contains the same
  `/opt/system-skills/gws/` content either way. This is a build-reliability and
  supply-chain change only.
- Renovate currently has no view of `GWS_VERSION`; whichever mechanism is chosen
  should not make version bumps harder to automate later.
