## 1. Branch and version

- [x] 1.1 Confirm `fix-k8s-log-bytes-repr` is merged — it touches the same file and the same spec, and is already deployed and verified
- [x] 1.2 Create branch `fix-premature-log-stream-termination` from an up-to-date `main`
- [x] 1.3 Bump `VERSION` — patch

## 2. Stop destroying evidence first

The smallest change with the largest effect, and independently valuable. Land it before the resume logic: on its own it converts destroyed work into a recoverable state, and it keeps the next occurrence available for diagnosis instead of deleting it.

- [x] 2.1 Write a failing test: cleanup is withheld when the exit code is unknown **and** the container is still running
- [x] 2.2 Write a test that cleanup still proceeds normally for a terminated container — this must not become a resource leak
- [x] 2.3 Implement the guard, and log when cleanup is withheld and why
- [x] 2.4 Confirm a withheld pod is still reclaimed by `ttlSecondsAfterFinished` (`K8S_JOB_TTL_SECONDS = 300`) and by orphaned-Job recovery, so nothing leaks

## 3. Make the interruption observable

Do this before the resume logic. The defect survived a week because a broken stream and a finished pod were indistinguishable; fixing that is what will let anyone confirm the resume actually works.

- [x] 3.1 Replace the bare `try`/`finally` in `_stream_logs()` so the worker records **why** it stopped — pod terminated, stream error, or stream ended with pod still running — rather than emitting the same sentinel for all three
- [x] 3.2 Add an explicit `except` around the stream iteration. Today an exception and a clean EOF are equally invisible
- [x] 3.3 Log "log stream ended while pod still running; resuming from <t>", naming the pod. This is the line whose absence made this hard to find

## 4. Resume instead of completing

- [x] 4.1 Write a failing test: with a stream that ends early and a pod still `Running`, the generator does **not** complete
- [x] 4.2 Write a failing test: with a stream that ends and a pod in a terminal phase, the generator **does** complete
- [x] 4.3 On stream end, read the pod phase and decide. Only `Succeeded`/`Failed` ends the run
- [x] 4.4 Resume with `since_time` (or `since_seconds`) anchored to the last line yielded, so the resumed stream neither repeats nor drops output — **`since_time` does not exist in the Kubernetes Python client (36.0.2); implemented as `timestamps=True` + a padded `since_seconds` + a per-line timestamp filter, which is exact rather than second-granular**
- [x] 4.5 Test continuity explicitly across a resume — no duplicated line, no missing line. The log feeds both the live viewer and the stored record, so a duplicate corrupts both
- [x] 4.6 Bound resumption by pod state, not by an attempt counter alone. A long task on a flaky connection is the case that most needs resuming, and a counter would abandon it. Add a generous attempt backstop underneath as a guard against a pathological loop
- [x] 4.7 Confirm a pod that genuinely dies — OOM, eviction — still ends the run promptly rather than being masked by resumption. The pod-phase check is what prevents this; test it
- [x] 4.8 Decide whether to fix the sync `run()` as well. It has the same shape and the same flaw; leaving it is how the two paths diverge — exactly the pattern that produced the bytes-repr bug in this same file

## 5. Verify

- [x] 5.1 Backend suite green: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`
- [x] 5.2 **Do not expect to reproduce the original trigger on demand.** It did not recur within a five-minute capture window and its cause is unknown. Tests inject a truncated stream at the client boundary, which proves the handling; it does not prove the trigger is gone
- [x] 5.3 Confirm the tests fail before the change. A test that only ever ran green afterwards proves nothing here

## 6. Ship

- [ ] 6.1 Commit, push, open a PR
- [ ] 6.2 CI green
- [ ] 6.3 Deploy to Kubernetes
- [ ] 6.4 Run a task that installs skill dependencies — the case that reliably failed — and confirm it completes
- [ ] 6.5 Confirm `Could not determine exit code for pod` no longer appears for tasks whose pods are still running. Query Loki: `{namespace="errand", container="server"} |= "Could not determine exit code"` — datasource `P8E80F9AEF21F6940`
- [ ] 6.6 Confirm no Job is deleted while its pod is `1/1 Running`, the state observed on `task-runner-6ac9fe38-brbtj`
- [ ] 6.7 Confirm live log streaming still works end to end — the change is inside the streaming path
- [ ] 6.8 Archive this change and commit the archive **as part of this PR** (see CLAUDE.md). Re-verify the redeploy afterwards — archiving produces a new image tag

## 7. Post-merge notes

Not tasks. The task list is frozen when the archive is committed, so anything that can only happen at or after the merge must not be a checkbox — see CLAUDE.md.

- Merge and delete the branch.
- Watch production for a few days: `Could not determine exit code` should disappear for running pods, and any new "resuming" log line indicates how often the underlying interruption actually occurs. That frequency is the measurement that would justify chasing the root cause.
- Re-run the tasks this destroyed if they are still wanted — `job hunt`, both `Nginx Access Log Analysis`, `Weekly Tech Research Summary`, `Process Blog URLs Twitter Posts`.

## 8. Follow-ups, not part of this change

Separate work, recorded so it is not lost.

- **Find the EOF trigger.** Unknown: candidates are an idle timeout during the quiet period after skill installation, an intermediate proxy, or client behaviour on an un-preloaded response. The cut is consistently right after `pip install` completes, which is a natural quiet gap. A live capture correlating pod phase against the "Streaming logs from pod" line would settle it, and might permit a simpler fix such as an explicit timeout.
- `result()` allows five seconds for a container to report termination. Probably too short, but with the stream fixed it is no longer the thing failing.
- **Suppress the retry when cleanup was withheld.** A task whose Job is left in place because its container is still running can still be retried, producing two live pods for one task. Rare (it needs the resume backstop exhausted or the stream to raise) and strictly better than today's "kill the work" resolution, but it is a real hole. Fixing it means touching retry policy, which this change excludes — `log_stream_outcome` on the handle is the signal a fix would read.
- Consider surfacing a task that has resumed many times. Silently resuming forever is its own blind spot, and a high resume count is a signal about the cluster rather than the task.
