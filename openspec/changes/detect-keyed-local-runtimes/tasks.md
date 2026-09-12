## 1. Branch and version

- [x] 1.1 Create branch `detect-keyed-local-runtimes` from an up-to-date `main`, after `local-ai-provider-detection` has merged
- [x] 1.2 Bump `VERSION` (minor — new API operation, new scan result field, new compose variable)

## 2. Recognise a keyed endpoint

- [x] 2.1 Write failing tests: a candidate answering 401 is reported as needing a key and creates no provider; one answering 403 likewise; one that does not respond is reported as neither; a mix of keyed and keyless endpoints reports each in the right place
- [x] 2.2 Add a detection-side reachability check that distinguishes "answered", "answered but unauthorised" and "no answer", without changing `probe_provider_type()` — the four call sites other than detection depend on `unknown` meaning what it means today
- [x] 2.3 Add the key-requiring runtimes to the scan result, alongside `detected` rather than inside it
- [x] 2.4 Confirm an empty scan still reports nothing found rather than failing, and that "detection unavailable" still probes nothing at all

Expect one benign divergence during manual testing, raised by the library side and not worth designing around: `needs_key` exclusion is computed server-side against configured providers, while the card holds scan results in local state and drops an entry when it adopts one. The two agree until a provider is *deleted* while a scan panel is open — the card's stale list still shows that endpoint as adopted, and the next scan correctly offers it again. Self-correcting, and a symptom of two sources of truth for a transient list rather than a fault in the exclusion rule.

## 3. Adoption

- [x] 3.1 Write failing tests: adopting with an accepted key creates a `source="detected"` provider carrying that key; a rejected key creates nothing and says so; an unreachable endpoint creates nothing and says so; the adopted endpoint stops being reported as needing a key
- [x] 3.2 Implement the adopt operation — probe with the supplied key, and create only on acceptance
- [x] 3.3 Take the provider name from the probe response obtained with the key (D2), not from the candidate table
- [x] 3.4 Expose it through the API as `POST /api/llm/providers/adopt-local`, returning 200 with `adopted` and a machine-readable `reason` (`key_rejected` / `unreachable` / `name_conflict`) rather than a status code the caller has to interpret — matching the reachability check, which already reports a finding as 200
- [x] 3.5 Carry `conflicting_name` on a `name_conflict` refusal, and accept an optional `name` so the caller can re-submit without renaming the other provider first
- [x] 3.6 Confirm adoption performs no scan and removes nothing — the constraint belongs where the deletion lives, not in the caller's restraint
- [x] 3.7 Confirm the adopted provider gets the raised detected-provider timeout, since that is the reason `source` matters here

## 4. Reconciliation with stored keys

- [x] 4.1 Write failing tests: an adopted runtime still accepting its key survives a re-scan; one rejecting the key is retained and shows unreachable; one that has stopped responding is removed; a stored key is sent only to its own endpoint and never to another candidate
- [x] 4.2 Look up an existing detected provider by base URL before probing a candidate, and probe with its key when one exists
- [x] 4.3 Retain a provider whose endpoint responds but rejects the stored key (D4) — a rotated key must not delete a user's provider
- [x] 4.4 Verify against a real keyed runtime that two consecutive scans leave the adopted provider intact

## 4b. A detected provider's endpoint is server-enforced, not UI-enforced

Found while fixing the rename bug in `local-ai-provider-detection`, and left there deliberately: the fix was already the third on that PR and this has no reported symptom.

`update_provider` refuses only `source == "env"`. The settings card locks a detected provider's base URL because the next scan reconciles that field — but the server accepts a change to it, so the guarantee is decorative. Editing it through the API points the row at an endpoint the scan will not match, and the next scan reconciles it away and clears the model settings that referenced it: the same data loss the rename fix removed, reached by the other field.

This belongs here because reconciliation is what this change reworks, and because the constraint should live where the deletion lives rather than in the caller's restraint — the same argument that made adoption's no-reconciliation a server requirement.

- [x] 4b.1 Write a failing test: changing a detected provider's base URL is refused; changing its name is not
- [x] 4b.2 Refuse base URL changes on `source="detected"` providers, with an error saying the endpoint is reconciled by scanning
- [x] 4b.3 Confirm the settings card's existing lock still behaves the same, so the two agree rather than merely coinciding

## 4c. The card cannot reach the routes it calls

Found while confirming 4b.3, and inseparable from it: a server-side guarantee on
a route the caller cannot reach is a guarantee that never runs.

`createDirectApi` sends `PATCH /api/llm/providers/{id}` and
`POST /api/llm/providers/{id}/default`; the server registered only `PUT` for
both, so each returned 405. On shipped v0.19.0 and current `main`, renaming a
provider, replacing its key and setting the default all fail from the settings
UI. `LlmProviderCardSeam.test.ts` cannot catch it — it injects a mock API
object, so the library's HTTP layer is never exercised, and it guards response
shapes rather than verbs.

Fixed here rather than deferred because 4b.2 has just moved a constraint onto
one of those exact routes.

This is half of the fix, and the half that reaches new deployments only. `PUT`
answers on every errand ever released and `PATCH` answers on none of them, so
the client that works everywhere is the `PUT` client — `errand-component-library`
is moving to it independently, which is what repairs already-deployed instances
that will never take this change. Accepting both verbs here is what lets an
*already shipped* card work against a new server, and it is additive: do not
later remove the second verb on the grounds that the library no longer sends
it, because the versions that do will remain in the wild.

- [x] 4c.1 Write a failing test: the card's verbs reach both routes, and the 4b.2 endpoint lock holds on the verb the card sends
- [x] 4c.2 Accept `PATCH` alongside `PUT` on the update route, and `POST` alongside `PUT` on the default route — both, not a swap, since an existing caller may already send either

## 4d. Adoption must not create a second provider at one endpoint

Found while capturing real responses for the cross-repo seam fixture, on the
deployed PR build. Adopting the same endpoint twice with different names
created two `source="detected"` rows at one `base_url`, after which the scan's
per-endpoint lookup raised `MultipleResultsFound` and every subsequent scan
returned 500 — permanently, until a row was deleted by hand.

This was considered during 3.2 and wrongly dismissed: the hazard was noted, and
a closed `reason` enum was allowed to override it. It contradicts the premise
the whole change rests on — that `base_url` is a detected provider's identity,
which D4, the endpoint lock and URL normalisation all depend on.

- [x] 4d.1 Write failing tests: a second adoption of one endpoint is refused and creates nothing; a supplied name does not bypass the check; an endpoint held by a provider of any source is refused; a scan survives duplicate rows already present
- [x] 4d.2 Refuse adoption of an endpoint that already has a provider, reporting `already_configured` with that provider's name — a fourth `reason` value, additive to the union a caller discriminates on
- [x] 4d.3 Remove the scan's `scalar_one_or_none()` per-endpoint lookup in favour of one deterministic pass, reconciling the earliest row and leaving duplicates in place rather than failing or deleting
- [x] 4d.4 State in the contract that `reason` is an open set and an unrecognised value must render `message` — adding the fourth value was not the additive change it looked like, because a consumer whose final branch was a specific reason misattributed it instead of falling through

## 5. Identification

- [x] 5.1 Write failing tests: an unreadable response on a singly-claimed port is not named after that runtime; a readable response with no marker still is
- [x] 5.2 Separate "no body read" from "body read, no marker" in `identify_runtime()`
- [x] 5.3 Confirm an oMLX server on 8000 is not registered as `vllm`

## 6. Port collision

- [x] 6.1 Write a failing test asserting both compose files publish the server through an overridable variable defaulting to 8000
- [x] 6.2 Change both compose files to `"${ERRAND_PORT:-8000}:8000"`
- [x] 6.3 Document the collision and the override beside the local-AI section of `README.md` — a user running a local runtime on 8000 needs to find this before they hit it, not after
- [x] 6.4 Verify the stack comes up with the override set while a local runtime holds 8000

## 7. Settings UI

Requires a `@errand-ai/ui-components` release and a consumer bump; everything above ships without it.

- [x] 7.1 Specify the scan-panel changes as an OpenSpec change in `errand-component-library` — key-requiring runtimes presented distinctly, a key field, an adopt action, and a rejected key explained without losing the entry
- [ ] 7.2 Implement and release it there
- [ ] 7.3 Bump the pin here and confirm the lockfile diff touches only that entry
- [ ] 7.4 Extend `frontend/src/components/__tests__/LlmProviderCardSeam.test.ts` with the new scan-result shape, captured from this repo's endpoint as the existing fixture was — the adopt call is a sixth response shape across the seam

## 8. Verify

- [x] 8.1 Run the full errand and frontend test suites
- [x] 8.2 End to end against the real keyed runtime: scan reports it as needing a key, adopt it with a real key, confirm it is named from its own response, select a model and run a task
- [x] 8.3 Confirm a keyless runtime on the same machine is still detected and registered exactly as before

## 9. Archive

- [ ] 9.1 `openspec archive detect-keyed-local-runtimes -y` and commit the result in this PR

## Post-merge notes

- The port collision is mitigated, not removed: a user who never sets `ERRAND_PORT` still cannot run a local runtime on 8000 beside the shipped compose.
- Worth revisiting whether `probe_provider_type()` should return a richer result than three strings, now that two callers want to distinguish "unauthorised" from "not there". Deliberately out of scope here — that probe has five call sites and this change should not be the one to reshape them.
