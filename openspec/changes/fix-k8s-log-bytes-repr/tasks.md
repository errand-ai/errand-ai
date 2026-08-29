## 1. Branch and version

- [x] 1.1 Create branch `fix-k8s-log-bytes-repr` from an up-to-date `main`
- [x] 1.2 Bump `VERSION` — patch. A defect fix; no interface changes

## 2. Write the failing test first

The reason this survived six months is that every plausible weak assertion passes against the corrupt value. `result()` does return logs; they are non-empty; they are a `str`. Only the shape of the string is wrong.

- [x] 2.1 Write a test for `KubernetesRuntime.result()` with a mocked client whose response body is realistic multi-line pod-log **bytes**. Assert the returned string contains real line-break characters, does **not** begin with `b'` or `b"`, and contains no literal backslash-`n` in place of line breaks
- [x] 2.2 Assert a stronger property: split the result on line breaks and confirm a line the task-runner emitted as a JSON event parses as a JSON object exposing `type`. This is what the log viewer actually does, and it is the assertion that ties the test to the symptom
- [x] 2.3 Confirm the test **fails on the current code** before changing anything. A test that only ever ran green after the fix proves nothing about this bug
- [x] 2.4 Mock at the client boundary, not at `result()`. Mocking the return value of `read_namespaced_pod_log` as a clean `str` reproduces nothing — the defect is in what the client does to bytes

## 3. Fix the read

- [x] 3.1 `errand/container_runtime.py:694` — read with `_preload_content=False` and decode the response explicitly, as `run()` does at `:643`
- [x] 3.2 Handle the changed return type. Preloading off yields a response object, not a string; read it fully and decode with `errors="replace"`, matching the streaming path's tolerance for malformed bytes
- [x] 3.3 Confirm `:694` was the only affected call. Every other `core_v1`/`batch_v1` call returns a typed model object rather than a `str`, so none hit the primitive-deserialisation path; the two streaming reads already pass `_preload_content=False`
- [x] 3.4 Leave `DockerRuntime` alone — it decodes explicitly at `:328-329` and is correct
- [x] 3.5 Note in the code *why* preloading is off. Without it the next reader sees a more complicated call than necessary and simplifies it back

## 4. Repair the existing rows

26 of 28 production tasks with logs are corrupt. Without this the fix appears not to work on anything that already exists.

- [x] 4.1 Write the migration's detection as a conjunction: starts with `b'` or `b"`, **and** ends with the matching quote, **and** contains no real line breaks, **and** `ast.literal_eval` yields a `bytes` object. Anything failing any condition is left alone
- [x] 4.2 Use `ast.literal_eval`, never `eval`
- [x] 4.3 Leave unrecoverable rows unchanged rather than partially rewriting them, and count them
- [x] 4.4 Test the repair against a truncated repr — `truncate_output` bounds stored logs by encoded byte length, so a long log may have lost its closing quote and must be skipped, not guessed at
- [x] 4.5 Test that a healthy log containing real line breaks is byte-for-byte unchanged, including one that legitimately begins with `b`
- [x] 4.6 Log a count of repaired and skipped rows so the result can be compared against the 26 measured in production
- [x] 4.7 Make the downgrade a no-op. Restoring corrupt data has no value, and pretending it is reversible is worse than declaring it is not

## 5. Verify

- [x] 5.1 Backend suite green: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`
- [x] 5.2 Confirm the section 2 tests now pass
- [x] 5.3 **Do not expect local docker-compose to show a difference.** `DockerRuntime` was always correct, so the bug cannot be reproduced or confirmed locally. This wants stating during review, because "I ran it locally and logs looked fine" is true both before and after
- [x] 5.4 Sanity-check the migration against a copy of real corrupt data rather than only synthetic fixtures

## 6. Ship

- [ ] 6.1 Commit, push, open a PR
- [ ] 6.2 CI green
- [ ] 6.3 Deploy to Kubernetes. Confirm a **newly run** task's completed logs render formatted — this is the actual fix
- [ ] 6.4 Confirm a **pre-existing** task's logs now render formatted — this is the backfill. Checking only new tasks leaves the migration unverified
- [ ] 6.5 Confirm live streaming still works on a running task. The change is next to the streaming path and must not disturb it
- [ ] 6.6 Confirm the `task_logs` MCP tool returns parseable logs for a completed task
- [ ] 6.7 Confirm the per-turn context-usage badge now appears on completed tasks — it has never rendered outside live streaming, because `llm_turn_end` events were entombed in the repr
- [ ] 6.8 Confirm errand-cloud renders completed task logs correctly, with **no change in that repository**. It binds the same `runner_logs` through a verbatim proxy into the same `@errand-ai/ui-components` 0.18.0
- [ ] 6.9 Archive this change and commit the archive **as part of this PR** (see CLAUDE.md). Re-verify the redeploy afterwards — archiving produces a new image tag

## 7. Post-merge notes

Not tasks. The task list is frozen when the archive is committed, so anything that can only happen at or after the merge must not be a checkbox — see CLAUDE.md.

- Merge and delete the branch.
- Confirm the migration ran on the production deployment and that its repaired/skipped counts match expectations.

## 8. Follow-ups, not part of this change

Separate work, recorded so it is not lost.

- `kubernetes>=36.0.2,<37` is a floating range on the library whose deserialisation behaviour caused this. Belongs with the constraints-file question, not here.
- The errand-cloud `{taskId}` template-literal bug is a separate defect in a separate repository, reportedly fixed in its PR #69. It broke live streaming there; it is unrelated to this one.
