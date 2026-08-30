## Why

`KubernetesRuntime.async_run()` treats the end of the pod log stream as proof the pod finished. It is not. When the stream reaches EOF early, the runtime reports the task complete, `result()` finds no terminated container and returns exit code `-1`, the task is retried, and `cleanup()` **deletes the Job — killing a container that is still doing work**. The retry repeats the whole cycle with exponential backoff, so an affected task can never finish while burning LLM tokens on every attempt.

Observed live on production: `task-runner-6ac9fe38-brbtj` was `1/1` **Running** while its Job was already `Terminating` at 114 seconds with `0/1` completions.

## Evidence

Six consecutive failures on 2026-08-30, from `errand-server` logs:

| Pod | "Streaming logs from pod" | "Could not determine exit code" | gap |
|---|---|---|---|
| `task-runner-abb5a4ce-grgdm` | …106.097 | …110.160 | 4.06s |
| `task-runner-9b5401fd-fm8tr` | …190.134 | …194.167 | 4.03s |
| `task-runner-e585e8d7-67kdk` | …207.178 | …211.223 | 4.04s |
| `task-runner-938532ba-pjd8q` | …273.098 | …277.163 | 4.06s |
| `task-runner-7e423411-579zk` | …348.144 | …352.201 | 4.05s |
| `task-runner-2ec83dd4-b86g6` | …421.054 | …425.097 | 4.04s |

That ~4.04s is arithmetic, not coincidence: it is exactly `result()`'s five attempts with four one-second sleeps between them. `async_run()` returns essentially the instant it has drained the log the pod had already produced.

**Not a new defect, and not caused by the log-decoding fix.** Loki shows the same failure across three deployment revisions over seven days — `errand-server-69f9cbdb7d` (`b364e7da`, five attempts), `errand-server-7bb49f548d` (`bb099ea6`, `410c1ce1`), and the current revision. `410c1ce1` is "Weekly Tech Research Summary", one of the cards already showing **Failed** on the board.

**Ruled out by evidence, not by argument:**

- *Container crashed and restarted* — the Job sets `restart_policy="Never"` and `backoff_limit=0`. No restarts occur.
- *The stream raised an exception* — no traceback from `container_runtime.py` appears anywhere in the server log for these runs. The stream ends **cleanly**.
- *Wrong container name* — the Job's container is named `task-runner`, which is what `result()` matches on.
- *The API call failed* — `result()` logs `Failed to read pod status` on `ApiException`. That message never appears; `read_namespaced_pod` succeeds and simply reports a container that has not terminated.

## The defect

`async_run`'s worker thread is `try` / `finally` with **no `except`**:

```python
def _stream_logs():
    try:
        log_stream = self.core_v1.read_namespaced_pod_log(
            pod_name, namespace, follow=True, _preload_content=False,
        )
        for chunk in log_stream:
            ...
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)   # sentinel, either way
```

A stream that broke and a pod that finished emit **the same sentinel**. Nothing downstream checks whether the pod actually reached a terminal phase before concluding the run is over, so any interruption — a proxy idle timeout, a connection reset, an API-server hiccup — is silently reinterpreted as "the task finished".

This is why the eventual symptom is so misleading. The task is marked failed for want of a result JSON that the agent had not reached yet, and the evidence is destroyed by `cleanup()` deleting the Job.

It also explains why *any* task ever succeeds: `task_manager` has an `exit_code != 0 but found valid structured output, treating as success` path, so `-1` is routinely tolerated. A task fails only when the stream dies **before** the agent emits its result JSON — which, for tasks that install skill dependencies, is exactly when it dies.

## What Changes

- Treat the end of the log stream as a **question**, not an answer. After the stream ends, confirm the pod reached a terminal phase (`Succeeded` or `Failed`). If it has not, the pod is still working and the run is not over.
- Resume streaming from where it stopped when the pod is still running, rather than returning. Kubernetes supports `since_time`/`since_seconds` for exactly this.
- Distinguish a broken stream from a finished pod in the worker: catch and record the failure rather than letting `finally` emit the same sentinel for both outcomes.
- **Never delete a Job whose container is still running with an unknown exit code.** This is the step that turns a recoverable stream glitch into destroyed work, and it is worth fixing even if everything above were left alone.
- Log the distinction, so "stream ended early, pod still running, resuming" is visible rather than silent.

**Not in scope:**

- The root cause of the EOF itself. It is not yet known whether it is an idle timeout, an intermediate proxy, or client behaviour — see the open question in `design.md`. The change above makes the system resilient to it either way, which is worth doing regardless of what the trigger turns out to be.
- `result()`'s five-second exit-code window. It is arguably too short, but with the stream fixed it is no longer the thing failing.
- `DockerRuntime` and `AppleContainerRuntime`, which do not use this streaming path.

## Capabilities

### Modified Capabilities

- `container-runtime`: the "KubernetesRuntime async methods" requirement says `async_run` "SHALL yield log lines as an async generator from the pod's log stream" and says nothing about when the generator is allowed to finish. That silence is the gap this defect lives in. It gains a requirement that the generator completes only once the pod has terminated.

## Impact

- **Code**: `errand/container_runtime.py` — `async_run` (and `run`, which has the same shape), and the Job-deletion path in `cleanup`/`task_manager`.
- **Live right now**: task `8e8e5b5a` is looping through this on production, and several REVIEW cards are its earlier victims.
- **Wasted spend**: every retry re-runs the agent from scratch, including re-installing skill dependencies, and is then killed. Backoff doubles to a 60-minute cap, so a task can churn for hours.
- **Risk of the fix**: a resume loop that never terminates would hang a task instead of failing it. Any resume must be bounded, and bounded by pod state rather than by attempt count alone.
- **Interaction with `fix-k8s-log-bytes-repr`**: both touch `container_runtime.py` and the `container-runtime` spec, but different functions and different requirements. That change should land first; it is already deployed and verified.
