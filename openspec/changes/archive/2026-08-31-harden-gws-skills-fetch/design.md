## Context

The `gws-builder` stage of `task-runner/Dockerfile` obtains the Google Workspace
CLI in two steps:

1. `curl` the `*-unknown-linux-musl` release tarball, verify it against the
   `.sha256` published beside it, install `gws` (lines 63–76).
2. `git clone --depth=1 --branch="v${GWS_VERSION}"` the whole repository, purely
   to copy `skills/gws-*` (line 79).

Step 2 runs once per architecture on every task-runner build. The repo root
`Dockerfile` has a near-identical `gws-skills` stage (lines 13-20) doing the same
unauthenticated clone of the same repository at the same tag, to populate
`/app/system-skills/gws/` in the server image via `COPY --from=gws-skills`
(line 69). Both are in scope.

An earlier draft of this document claimed the task-runner clone was the *only*
unauthenticated git operation in the repo's builds. That was wrong — the server
image does the same thing, and only chance spared `build-errand` during the
outage. Both `build-task-runner` and `build-errand` are required jobs.

Evidence gathered while diagnosing the PR #251 outage:

- **The failure is transport-specific, not connectivity.** In every failed build
  the stage reached instruction 4/4 — meaning the `curl` in step 1, to
  `github.com` release assets, had already succeeded on the same architecture in
  the same stage moments earlier. Only the git clone failed, with
  `fatal: could not read Username for 'https://github.com'` (what git does when
  the server answers 401/404 and it falls back to prompting).
- **Release assets do not contain the skills.** Extracting
  `google-workspace-cli-aarch64-unknown-linux-musl.tar.gz` yields exactly
  `./gws`, `./README.md`, `./LICENSE`, `./CHANGELOG.md`. There is no skills
  asset on the release, so the skills genuinely have to come from source.
- **The payload is small.** `skills/gws-*` at v0.22.5 is 44 directories, 95
  files, 408K of markdown. The full source archive is 1.1M — smaller than a
  shallow clone of the repo.
- **The failure is intermittent, not permanent.** Four consecutive builds failed
  over roughly four hours; a fifth, with no changes, succeeded. Consistent with
  rate limiting on unauthenticated git from the self-hosted runner's fixed IP,
  though not proven.

## Goals / Non-Goals

**Goals**
- Remove the dependency on anonymous git from **both** image builds.
- Keep `GWS_VERSION` the single source of truth for both the binary and its
  skills, so the two cannot drift apart.
- Keep a credential-free `docker build` working for contributors.
- Give CI authenticated rate limits where a credential is available.

**Non-Goals**
- Changing which skills ship, or their content or location in the final image
  (`/opt/system-skills/gws/`).
- Introducing byte-level integrity verification of the skills. See Decision 3.
- Fixing action SHA-pinning, or any other supply-chain hardening not on this
  path. Raised in review on PR #251 and deliberately left out.
- Automating `GWS_VERSION` bumps via Renovate.

## Decisions

### Decision 1: Fetch the source archive with `curl`, not git — in both images

Replace each clone with a `curl` of
`https://codeload.github.com/googleworkspace/cli/tar.gz/refs/tags/v${GWS_VERSION}`,
extract, and copy `skills/gws-*` out.

This uses the same tool, and the same class of endpoint, as the binary fetch
that demonstrably kept working through every failure in the same stage. It is
also cheaper: 1.1M for the archive against a shallow clone that pulls the whole
tree plus git metadata, twice per build.

Alternatives rejected:

- *Authenticate the existing clone.* Raises the rate limit but keeps the exact
  transport that failed, and makes a token effectively mandatory for a reliable
  build. It also leaves the skills unverified, so it buys reliability alone.
- *Vendor the skills in-tree.* Genuinely attractive — it removes the build-time
  network dependency outright and makes the skill text reviewable in diffs,
  which matters because this content lands in the agent's prompt surface. But
  every `GWS_VERSION` bump becomes a 95-file diff that no tool can generate for
  us, and keeping the vendored copy honest needs its own CI drift check against
  the upstream tag. That is a larger, separate change; revisit it if fetching
  proves unreliable again.

### Decision 2: Apply the identical mechanism to both images

The two stages differ only in their output path (`/gws-skills` copied to
`/opt/system-skills/gws/` in the task-runner, `/app/system-skills/gws/` in the
server) and in platform pinning — the server's stage is
`--platform=$BUILDPLATFORM` because SKILL.md files are architecture-independent,
which is worth preserving. Everything else — URL, token handling, glob, guard —
is the same text.

Keeping them identical is deliberate: two subtly different fetches of the same
artefact is how one gets fixed and the other rots. The duplication is accepted
rather than factored into a shared stage, because the two Dockerfiles have
separate build contexts and no shared base, and a shared stage would couple the
server image's build to the task-runner's for no benefit.

Alternative rejected: *fix only the task-runner and follow up on the server.*
The exposure is identical and the fix is the same text; deferring it leaves a
required job carrying a known intermittent failure, and would make this change's
own claim to have removed the dependency untrue.

### Decision 3: Send a token when one is present, never require it

Mount a `github_token` build secret and add an `Authorization: Bearer` header
only when the secret file exists, mirroring the `npm_token` handling already in
the root `Dockerfile`:

```
RUN --mount=type=secret,id=npm_token \
    if [ -f /run/secrets/npm_token ]; then ... fi && npm ci
```

CI passes `secrets: github_token=${{ secrets.GITHUB_TOKEN }}` on both the
`build-task-runner` job (which currently passes no secrets at all) and
`build-errand` (which already passes `npm_token`), so CI gets authenticated
limits for both. A contributor running `docker build` with no secret still
succeeds against the public endpoint — the same property the npm_token pattern
gives today.

Alternatives rejected:

- *Require the token unconditionally.* Moves a CI-only failure onto every
  contributor and makes the image unbuildable outside this org.
- *Bake a token into a build arg.* Build args are recorded in image history;
  `--mount=type=secret` is not. Not a real option.

### Decision 4: Sanity-check the extraction; do not pin an archive checksum

After extraction, assert that `skills/gws-*` yielded at least one directory
containing a `SKILL.md`, and fail the build loudly otherwise. Do not pin a
SHA256 of the source archive.

Two fetches of the v0.22.5 archive minutes apart returned an identical digest
(`1e55ec8c…`), but GitHub does not guarantee auto-generated source archives are
byte-stable, and has changed their generation before. A pinned hash would
therefore convert a rare intermittent failure into a guaranteed hard failure at
an unpredictable future date — a worse trade for a build that is not currently
verifying this content at all.

The check that matters here is *did we actually get skills*, because the failure
mode a silent empty copy produces is a task-runner image that looks fine and
quietly has no Google Workspace skills. That is worth failing the build over;
byte-identity with an upstream archive is not, at this level of assurance.

Alternatives rejected:

- *Pin the archive SHA256.* Fragile for the reason above.
- *Fetch by commit SHA rather than tag.* Genuinely more tamper-evident, since a
  tag can be moved and a commit cannot. Rejected only because it adds a second
  value to bump in lockstep with `GWS_VERSION`, with no mechanism to keep them
  consistent — the drift it introduces is more likely to bite than the tag
  movement it defends against. Worth reconsidering alongside vendoring.

## Risks / Trade-offs

- **codeload is rate-limited too, and could fail the same way.** → Mitigated by
  Decision 3 (authenticated in CI). Not eliminated: this remains a build-time
  network dependency. If it recurs, vendoring (Decision 1's rejected
  alternative) is the escalation.
- **The archive's top-level directory name is derived from the tag**
  (`cli-0.22.5/`). A tag naming change upstream would break the copy path. →
  Mitigated by globbing the extracted root rather than hardcoding
  `cli-${GWS_VERSION}`, and by the Decision 4 sanity check turning a silent
  miss into a build failure.
- **No integrity verification of skill content.** → Accepted, and no worse than
  today: the current clone verifies nothing either. Decision 4 states why
  byte-pinning is not the right answer at this level.
- **A token in CI slightly widens what the build can reach.** → `GITHUB_TOKEN`
  is already available to the job and used for ghcr login; scope is unchanged.

## Migration Plan

None required. The change is confined to a builder stage; the final image
contents are byte-identical in intent (`/opt/system-skills/gws/` with the same
SKILL.md files at the same pinned version). Rollback is reverting the commit.

Verification is that `build-task-runner` succeeds on both architectures and the
existing `task-runner-image` scenario "gws skills are bundled" still holds
against the built image.

## Open Questions

- Should `GWS_VERSION` bumps be automated? Renovate has no view of it today, so
  the binary and skills are pinned by hand. Out of scope here, but the longer it
  stays manual the more likely the pin goes stale.
- If codeload proves as unreliable as anonymous git, vendoring becomes the
  answer. Worth a decision point rather than a third fetch mechanism.
