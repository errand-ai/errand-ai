## Context

Live task logs are delivered to the frontend via Server-Sent Events from `GET /api/tasks/{task_id}/logs/stream`. The endpoint subscribes to a Valkey pub/sub channel `task_logs:{task_id}` populated by the task manager (`errand/task_manager.py`) as the runner emits events to stderr.

Pub/sub has no replay: a subscriber receives only messages published after subscription. This is fine while a viewer is already open, but it makes opening the modal mid-run feel broken — the user sees only "Waiting for logs..." until the next event happens to fire. For agent tasks, the gap between events can be tens of seconds (model thinking, long tool calls, network I/O), so users routinely give up before any output arrives.

`runner_logs` on the `Task` row is unhelpful here because the task manager only writes it when a run finishes (success path) or when scheduling a retry. There is no "current accumulated output" anywhere accessible to the SSE handler while a task is running.

## Goals / Non-Goals

**Goals:**
- When the modal opens against a running task, the user immediately sees every event that has been published for the task so far, then continues to receive new events live.
- No protocol change visible to the frontend: replayed events arrive on the same SSE stream as live ones and are rendered by the same code path.
- Bound the per-task buffer size and lifetime so a chatty or long-running task cannot exhaust Valkey memory.

**Non-Goals:**
- Persistent log history across server restarts — buffer lives in Valkey only and may be lost if Valkey loses data; the existing `runner_logs` field still owns the post-completion snapshot.
- Replay for viewers connected during a network blip (no per-client cursor / resume token).
- Changing how logs are stored after task completion (the existing `runner_logs` text column is unchanged).
- Surfacing buffered logs anywhere except the live-mode SSE stream.

## Decisions

### Decision 1: Use a Valkey LIST as the buffer, not a Stream

**Choice:** `RPUSH task_logs_buffer:{task_id} <event_json>` followed by `LTRIM task_logs_buffer:{task_id} -<N> -1` per publish, where N is the configured cap (default 5,000). On connect, SSE reads with `LRANGE 0 -1`. The list is deleted when `task_log_end` is published (or the task ends for any reason) and is given a TTL as a safety net.

**Rationale:** Lists are O(1) for `RPUSH` and trivial to read in order with `LRANGE`. Streams (XADD/XRANGE) would also work and offer per-consumer cursors, but we don't need cursors — every reconnect re-reads the full buffer — and Streams add operational complexity (consumer groups, trimming policies) that buys nothing for this use case. The list shape mirrors the existing publish loop most cleanly.

**Alternatives considered:**
- *Redis Streams:* richer, but unused features. Adds ops complexity.
- *In-process buffer in the server:* doesn't survive across replicas; SSE may be served by a replica that didn't run the task. Rejected because the task manager only runs on the leader replica but SSE serves from all replicas.
- *Read from container stdout on demand:* requires re-attaching to a running container, which the runtime abstraction doesn't expose; events would also be unparsed.

### Decision 2: Subscribe to pub/sub *before* reading the buffer

**Choice:** In the SSE handler, call `pubsub.subscribe(...)` first, *then* `LRANGE` the buffer, emit those entries, *then* enter the live message loop. Live messages that arrive during the LRANGE are queued by the Valkey client and emitted after the replay.

**Rationale:** This is the standard "subscribe-then-snapshot" ordering for replay-without-loss. If we read the buffer first, an event published between LRANGE and SUBSCRIBE would be lost.

**Trade-off:** A handful of events at the boundary may be emitted twice — once from the buffer, once from pub/sub — because the buffer write and pub/sub publish are not atomic. We accept this; the renderer is idempotent (duplicate `tool_call` / `tool_result` events render twice but don't crash). Adding a per-event ID + dedup is more complexity than this fix needs. See risks below.

**Alternatives considered:**
- *Pause publishing during snapshot:* not possible with pub/sub fan-out across multiple subscribers without coordination.
- *Per-event monotonic ID + client-side dedup:* viable but raises the cost of the fix significantly. Defer until duplicates are observed to be a real problem.

### Decision 3: Buffer cap of 5,000 events with TTL of 24 hours

**Choice:** Cap the list at 5,000 entries via `LTRIM`. Set `EXPIRE task_logs_buffer:{task_id} 86400` on every push so an orphaned buffer (server crash before `task_log_end`) doesn't live forever.

**Rationale:** Average event JSON is ~500 bytes – 1 KB; 5,000 entries ≈ 2.5–5 MB per running task. With a typical concurrency cap of 3, worst-case memory is ~15 MB across the buffer. A 24-hour TTL is comfortably longer than any realistic task and far shorter than a Valkey persistence cycle, so orphans clear without operator action. Both numbers are settings — `task_log_buffer_max_entries` and `task_log_buffer_ttl_seconds` — so they can be tuned without a redeploy.

**Trade-off:** A run that emits more than 5,000 events before a viewer opens will lose its earliest events from the replay. That's acceptable: those events were already missing from the modal pre-fix, and the cap is generous compared to typical task volumes.

### Decision 4: Buffer cleanup on `task_log_end`

**Choice:** Immediately after publishing `task_log_end`, the task manager deletes the buffer (`DEL task_logs_buffer:{task_id}`). The TTL is the safety net only.

**Rationale:** Once the task ends, the SSE endpoint sends `task_log_end` and switches static-mode viewers to use `runner_logs` from the DB. The buffer's job is done. Deleting it eagerly keeps Valkey memory tight.

### Decision 5: No frontend code change to the live-mode renderer

**Choice:** The replay events flow through the existing `data:` SSE messages, parsed by the existing `task_event` handler. The "Waiting for logs..." placeholder is already conditional on the events array being empty, so it disappears as soon as the first replayed event arrives. The spec is updated to make this behaviour explicit, but no code change is required in the modal.

**Rationale:** Keeps the surface area of the fix small and avoids regressing the unrelated static mode.

## Risks / Trade-offs

- **Duplicate events at the subscribe/snapshot boundary** → accepted; renderer tolerates duplicates and the visual cost is minor (a tool call rendered twice). Revisit if user reports show this is confusing.
- **Buffer write failure leaves a partial backlog** → publish is best-effort already (`logger.warning("Failed to publish log line to Valkey")`); buffer write follows the same pattern. A failed buffer push is logged and the live publish still happens, so live viewers continue to work even if replay misses some events.
- **Buffer outgrows the cap on very chatty tasks** → cap is exposed as a setting and the trim is O(1) per push; operator can raise the limit if needed.
- **Memory pressure on Valkey** → bounded: cap × concurrency × ~1 KB, TTL backstop. Same Valkey instance already handles the pub/sub fan-out, so this is incremental load, not new infrastructure.
- **Race between `DEL` and a slow viewer mid-replay** → the SSE handler has already issued `LRANGE` before any `DEL` could happen for that task (since `task_log_end` triggers both the buffer delete and the SSE handler's exit), so a viewer that connected pre-end will finish its replay from the in-flight list snapshot.

## Migration Plan

- **Deploy:** rolling restart. Old replicas continue serving live SSE without replay; new replicas serve with replay. Mixed-mode operation is safe because the buffer is written by the task manager (single leader) and read by any SSE replica — old replicas simply ignore the new key. Once the new task manager is leader, all subsequent runs get a buffer.
- **Backfill:** none. Tasks already running at deploy time will have a partial backlog (only events emitted after the new leader takes over); fully-buffered replay applies to tasks started after the new task manager binds the advisory lock.
- **Rollback:** revert. Buffers self-expire within 24h. No schema change to undo.

## Open Questions

- Should we expose the buffer size as a per-environment Helm value, or only as an admin setting in the DB? Current plan: admin setting (consistent with `max_concurrent_tasks`); add a Helm value only if operators ask.
