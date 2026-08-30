## Context

The runtime infers pod completion from a side effect — the log stream ending — rather than from pod state. That inference is correct most of the time, which is why it has survived, and catastrophic when it is wrong: the task is failed, retried, and its still-running container is deleted.

The failure is silent in every direction. No exception is raised, no error is logged, and the evidence is destroyed by `cleanup()`. What reaches a human is a task marked "Failed" with truncated logs, which reads as the agent having crashed rather than as the platform having killed it.

One property shapes the whole design: **errand cannot tell, from the stream alone, why the stream ended.** EOF on a `follow=True` request is what you get when the pod finishes *and* what you get when the connection drops. The only authority on whether the pod finished is the pod's own phase, and the fix is essentially "go and ask".

## Goals / Non-Goals

**Goals:**

- A task whose log stream is interrupted continues to completion instead of being failed and killed.
- Stream interruption is visible in the logs rather than indistinguishable from success.
- No Job is deleted while its container is still running and its exit code is unknown.
- The stored log for a resumed run is continuous — no gap, no duplicated block.

**Non-Goals:**

- Diagnosing the EOF trigger. Worth knowing, not worth blocking on; see Open Questions.
- Widening `result()`'s exit-code window.
- `DockerRuntime` / `AppleContainerRuntime`.
- Any change to retry policy or backoff. With the stream fixed, these tasks should not reach the retry path at all.

## Decisions

**Ask the pod, not the stream.** After the log stream ends, read the pod's phase. `Succeeded` or `Failed` means the run is genuinely over. Anything else means the pod is still working and the stream lied. This inverts the current logic: today, stream EOF is the authority and pod state is consulted only afterwards, in `result()`, where a non-terminal state is treated as an error (`-1`) rather than as a signal to keep going.

**Resume with `since_time`, not from the beginning.** A resumed stream must not re-yield what was already emitted; the log is published live to Valkey and persisted, so duplicates would corrupt both. Kubernetes accepts `since_time` (and `since_seconds`), so the resume can request only what followed the last line. The alternative — re-reading and de-duplicating — is more code and more ways to be wrong.

**Bound the resume by pod state, not by an attempt counter alone.** A pure retry cap is the obvious guard and the wrong primary one: a long-running task with a flaky connection is exactly the case that needs resumption most, and a counter would give up on it. The natural bound is the pod itself — keep resuming while the pod is running, stop when it terminates. A generous attempt cap belongs underneath that as a backstop against a pathological loop, not as the main control.

**Separate "stream broke" from "pod finished" in the worker.** Today `finally` emits the same sentinel for both. The worker should record *why* it stopped, so the consumer can act on it. This is what makes the difference observable, and observability here is most of the value — the defect went unnoticed for a week because a broken stream looked exactly like a successful one.

**Do not delete a Job whose container is still running with an unknown exit code.** This is a smaller change than the resume logic and independently worth making. If everything above were wrong, this alone would turn destroyed work into a recoverable state. It is also the part that makes the failure irreversible today: once the Job is gone, so is the container, its output, and any chance of diagnosing what happened.

**Log the interruption.** "Log stream ended while pod still running; resuming from <t>" is the line whose absence made this hard to find.

## Risks / Trade-offs

**A resume loop that never terminates hangs the task instead of failing it** → The main risk the fix introduces, and a worse failure than the one being fixed, because a hung task occupies a concurrency slot indefinitely. Bounded by pod state, with an attempt backstop; a task whose pod is genuinely gone must still fail.

**Duplicated or missing log lines across a resume** → `since_time` has second granularity, so lines sharing a second with the last received one may repeat or drop. Worth checking against a real resumed run rather than reasoning about, since the log feeds both the live viewer and the stored record.

**The fix cannot be verified without reproducing the EOF** → The trigger is not yet understood and did not reproduce inside a five-minute capture window. A test can inject a truncated stream at the client boundary, which proves the handling; proving the real trigger is resolved needs production observation over time.

**Masking a genuine pod failure** → If a pod is being killed for a real reason — OOM, eviction, node pressure — resuming the stream could turn a fast clear failure into a slow confusing one. The pod-phase check is what prevents this: a killed pod reaches a terminal phase, and the run ends.

**Concurrent behaviour** → `async_run` runs its reader in an executor thread and marshals lines back through a queue. Adding resume logic adds state to that seam. The existing shape is already subtle; the change should not make it more so.

## Migration Plan

No schema change, no data migration, no configuration. Code only.

Land after `fix-k8s-log-bytes-repr`, which touches the same file and is already deployed and verified. Rollback is a version revert; the failure mode returns but nothing is left inconsistent.

Verification is unusual for this change: the bug is a race that did not reproduce on demand. Confidence comes from a test that injects a truncated stream, plus watching production for the disappearance of `Could not determine exit code` alongside tasks that previously looped.

## Open Questions

- **What actually causes the EOF?** Unknown. Candidates: an idle timeout on the connection during the quiet period while the agent starts after skill installation; an intermediate proxy between errand and the API server; or client-side behaviour when iterating an un-preloaded response. It is suspicious that the observed cut is consistently right after the skill `pip install` completes — a natural quiet gap. A live capture correlating pod phase against errand's "Streaming logs from pod" line would settle it. The fix does not depend on the answer, but the answer might permit a simpler one, such as setting an explicit timeout.
- **Should `run()` be fixed too, or only `async_run()`?** Production uses the async path. The sync `run()` has the same shape and the same flaw, and leaving it is how the two paths diverge — the pattern that produced the bytes-repr bug in this very file.
- **Is `since_time`'s one-second granularity sufficient?** If not, the resume needs a different anchor — a byte offset or a line count — and neither is offered by the Kubernetes log API.
- **Should a task whose stream broke repeatedly be surfaced differently?** Silently resuming forever is its own blind spot. A task that has resumed many times is a signal about the cluster, not about the task.
