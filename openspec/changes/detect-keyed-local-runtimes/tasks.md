## 1. Branch and version

- [ ] 1.1 Create branch `detect-keyed-local-runtimes` from an up-to-date `main`, after `local-ai-provider-detection` has merged
- [ ] 1.2 Bump `VERSION` (minor — new API operation, new scan result field, new compose variable)

## 2. Recognise a keyed endpoint

- [ ] 2.1 Write failing tests: a candidate answering 401 is reported as needing a key and creates no provider; one answering 403 likewise; one that does not respond is reported as neither; a mix of keyed and keyless endpoints reports each in the right place
- [ ] 2.2 Add a detection-side reachability check that distinguishes "answered", "answered but unauthorised" and "no answer", without changing `probe_provider_type()` — the four call sites other than detection depend on `unknown` meaning what it means today
- [ ] 2.3 Add the key-requiring runtimes to the scan result, alongside `detected` rather than inside it
- [ ] 2.4 Confirm an empty scan still reports nothing found rather than failing, and that "detection unavailable" still probes nothing at all

## 3. Adoption

- [ ] 3.1 Write failing tests: adopting with an accepted key creates a `source="detected"` provider carrying that key; a rejected key creates nothing and says so; an unreachable endpoint creates nothing and says so; the adopted endpoint stops being reported as needing a key
- [ ] 3.2 Implement the adopt operation — probe with the supplied key, and create only on acceptance
- [ ] 3.3 Take the provider name from the probe response obtained with the key (D2), not from the candidate table
- [ ] 3.4 Expose it through the API as `POST /api/llm/providers/adopt-local`, returning 200 with `adopted` and a machine-readable `reason` (`key_rejected` / `unreachable` / `name_conflict`) rather than a status code the caller has to interpret — matching the reachability check, which already reports a finding as 200
- [ ] 3.5 Carry `conflicting_name` on a `name_conflict` refusal, and accept an optional `name` so the caller can re-submit without renaming the other provider first
- [ ] 3.6 Confirm adoption performs no scan and removes nothing — the constraint belongs where the deletion lives, not in the caller's restraint
- [ ] 3.7 Confirm the adopted provider gets the raised detected-provider timeout, since that is the reason `source` matters here

## 4. Reconciliation with stored keys

- [ ] 4.1 Write failing tests: an adopted runtime still accepting its key survives a re-scan; one rejecting the key is retained and shows unreachable; one that has stopped responding is removed; a stored key is sent only to its own endpoint and never to another candidate
- [ ] 4.2 Look up an existing detected provider by base URL before probing a candidate, and probe with its key when one exists
- [ ] 4.3 Retain a provider whose endpoint responds but rejects the stored key (D4) — a rotated key must not delete a user's provider
- [ ] 4.4 Verify against a real keyed runtime that two consecutive scans leave the adopted provider intact

## 5. Identification

- [ ] 5.1 Write failing tests: an unreadable response on a singly-claimed port is not named after that runtime; a readable response with no marker still is
- [ ] 5.2 Separate "no body read" from "body read, no marker" in `identify_runtime()`
- [ ] 5.3 Confirm an oMLX server on 8000 is not registered as `vllm`

## 6. Port collision

- [ ] 6.1 Write a failing test asserting both compose files publish the server through an overridable variable defaulting to 8000
- [ ] 6.2 Change both compose files to `"${ERRAND_PORT:-8000}:8000"`
- [ ] 6.3 Document the collision and the override beside the local-AI section of `README.md` — a user running a local runtime on 8000 needs to find this before they hit it, not after
- [ ] 6.4 Verify the stack comes up with the override set while a local runtime holds 8000

## 7. Settings UI

Requires a `@errand-ai/ui-components` release and a consumer bump; everything above ships without it.

- [ ] 7.1 Specify the scan-panel changes as an OpenSpec change in `errand-component-library` — key-requiring runtimes presented distinctly, a key field, an adopt action, and a rejected key explained without losing the entry
- [ ] 7.2 Implement and release it there
- [ ] 7.3 Bump the pin here and confirm the lockfile diff touches only that entry
- [ ] 7.4 Extend `frontend/src/components/__tests__/LlmProviderCardSeam.test.ts` with the new scan-result shape, captured from this repo's endpoint as the existing fixture was — the adopt call is a sixth response shape across the seam

## 8. Verify

- [ ] 8.1 Run the full errand and frontend test suites
- [ ] 8.2 End to end against the real keyed runtime: scan reports it as needing a key, adopt it with a real key, confirm it is named from its own response, select a model and run a task
- [ ] 8.3 Confirm a keyless runtime on the same machine is still detected and registered exactly as before

## 9. Archive

- [ ] 9.1 `openspec archive detect-keyed-local-runtimes -y` and commit the result in this PR

## Post-merge notes

- The port collision is mitigated, not removed: a user who never sets `ERRAND_PORT` still cannot run a local runtime on 8000 beside the shipped compose.
- Worth revisiting whether `probe_provider_type()` should return a richer result than three strings, now that two callers want to distinguish "unauthorised" from "not there". Deliberately out of scope here — that probe has five call sites and this change should not be the one to reshape them.
