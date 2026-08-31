## 1. Replace the clone in the gws-builder stage

- [x] 1.1 In `task-runner/Dockerfile`, replace the `git clone` at line 79 with a `curl` of `https://codeload.github.com/googleworkspace/cli/tar.gz/refs/tags/v${GWS_VERSION}`, extracting `skills/gws-*` into `/gws-skills/`
- [x] 1.2 Glob the extracted root rather than hardcoding `cli-${GWS_VERSION}/`, so an upstream change to the archive's top-level directory name does not silently break the copy
- [x] 1.3 Mount a `github_token` build secret and add `-H "Authorization: Bearer …"` only when `/run/secrets/github_token` exists, mirroring the `npm_token` pattern in the root `Dockerfile:5-9`
- [x] 1.4 Fail the stage if no `gws-*` directory containing a `SKILL.md` was extracted, with a message naming the URL attempted
- [x] 1.5 Confirm `git` is still needed in the `gws-builder` stage's `apt-get install`; drop it from that stage if nothing else uses it (it is installed separately in `git-builder` for the final image)

## 2. Pass the token in CI

- [x] 2.1 Add `secrets: github_token=${{ secrets.GITHUB_TOKEN }}` to the `build-task-runner` job's `docker/build-push-action` step in `.github/workflows/build.yml` (that job currently passes no secrets)
- [x] 2.2 Leave every other job untouched — no other build consumes the gws skills

## 3. Verify locally before pushing

- [x] 3.1 `docker build -f task-runner/Dockerfile --platform linux/arm64 -t tr-test .` with **no** secret — must succeed (the credential-free path)
- [x] 3.2 Confirm the built image has 44 `gws-*` skill directories under `/opt/system-skills/gws/`, each with a `SKILL.md`, matching what the clone produced at v0.22.5
- [x] 3.3 Build again passing a `github_token` secret and confirm the image contents are identical to 3.1
- [x] 3.4 Force the failure path (e.g. build with a bogus `GWS_VERSION`) and confirm the build fails loudly rather than producing an image with an empty `/opt/system-skills/gws/`
- [x] 3.5 Confirm `gws --version` still works in the built image (the binary fetch is untouched, but the stage was edited)

## 4. Ship

- [x] 4.1 Bump `VERSION` (patch — build-only change, no runtime behaviour difference)
- [x] 4.2 Push, open PR, confirm `build-task-runner` passes on **both** `linux/amd64` and `linux/arm64` (the arm64 QEMU leg is where the clone failed)
- [x] 4.3 Confirm the `helm` job runs — it was skipped whenever `build-task-runner` failed
- [x] 4.4 Verify the CI-built artifact rather than a live task run: pulled `errand-task-runner:0.147.1-pr252.1185` for `linux/arm64` (the previously failing leg) and confirmed `/opt/system-skills/gws/` holds 44 directories / 44 `SKILL.md` with a file listing identical to upstream's `gws-*` subset, plus working `gws` and `git`. This tests the actual published image and the guard's intent — a silently empty skills directory — more directly than a task run, which only exercises whichever skills that task happens to use

## 5. Archive

- [x] 5.1 `openspec archive harden-gws-skills-fetch -y` and commit the flattened specs in this PR

## Post-merge notes

- Re-verify the post-archive build. `build.yml` carries `paths-ignore: openspec/**`,
  but on a `pull_request` event that is evaluated against the PR's whole diff, not
  the pushed commit — this PR touches code, so the archive push rebuilds and
  supersedes the tag verified in section 4.
- If codeload proves as unreliable as anonymous git, escalate to vendoring the
  408K of skills in-tree (design.md, Decision 1, rejected alternative). That
  needs its own drift check against `GWS_VERSION`.
- `GWS_VERSION` is still bumped by hand; Renovate has no view of it. Worth its
  own change before the pin goes stale.
