## Context

A one-line defect with a wide blast radius and an awkward property: it is invisible everywhere except production. `DockerRuntime` decodes explicitly, so local docker-compose is correct; the bug needs `CONTAINER_RUNTIME=kubernetes` to appear. It has been live since 2026-02-22 without being noticed, because the symptom — logs that look unformatted — reads as a cosmetic frontend issue rather than corrupt stored data.

Two things make it more than cosmetic. The corrupted string is what the `task_logs` MCP tool hands an agent, so a model reading a completed task's logs gets an unparseable blob. And the per-turn token accounting shipped in `context-usage-observability` is entombed in it — those events exist in the log, but nothing downstream can reach them once they are inside a repr.

## Goals / Non-Goals

**Goals:**

- A completed task's logs render identically to the same task's live stream.
- The two log paths in `KubernetesRuntime` obtain text by the same mechanism, so they cannot drift apart again.
- Existing corrupted rows are repaired, not just newly-written ones.
- A test that fails on the current code.

**Non-Goals:**

- Making the log viewer tolerate a bytes repr. The stored data is wrong.
- Pinning the kubernetes client. Real concern, separate argument.
- Any change to live streaming, which is correct.
- Re-encoding or restructuring what the task-runner emits.

## Decisions

**Use `_preload_content=False` and decode explicitly, rather than repairing the returned string.** Two fixes work. The narrow one detects a `b'...'` result and reverses it. The structural one stops asking the client to deserialise at all, and decodes the raw stream exactly as `run()` already does. The structural fix is better for a reason beyond taste: after it, both call sites in the class read logs the same way, so a future reader cannot look at one and reasonably conclude the other is equivalent. That similarity is what made this bug survive — the two calls sit 150 lines apart and look interchangeable.

**Assert on newlines, not on emptiness.** The test that would have caught this is not "result() returns logs" — that passes today. It is "the returned string contains real `\n` characters and does not begin with `b'`". Any weaker assertion is satisfied by the corrupt value, which is exactly how a bytes repr passed for six months.

**Backfill rather than repair-on-read.** A read-time fallback in the API layer would fix the display for old and new rows in one place, and is tempting. It is the wrong choice: it leaves corrupt data in the database, it has to be applied in every consumer (`/api/tasks`, the MCP tool, anything future), and it becomes permanent because nothing ever forces its removal. A one-off migration ends the problem. The cost is that it is a data migration and therefore one-way.

**Be conservative about what the backfill treats as corrupt.** The detection cannot simply be "starts with `b'`". A genuine log could, however unlikely, begin that way. The safe test is conjunctive: the value starts with `b'` **and** ends with `'` **and** contains zero real newline characters **and** `ast.literal_eval` returns a `bytes` object. A row failing any of those is left alone. `ast.literal_eval` is the right tool over `eval` because it evaluates literals only.

**Do not attempt to recover unparseable rows.** If `literal_eval` raises, or decoding the result fails, the migration leaves that row exactly as it is rather than guessing. A log that cannot be recovered cleanly is better left visibly wrong than silently mangled further.

## Risks / Trade-offs

**The backfill corrupts a row it misjudged** → The only genuinely dangerous part of this change, because it rewrites real data one-way. Mitigated by the conjunctive detection above, by leaving anything ambiguous untouched, and by counting affected rows before and after so the number can be compared against the 26 measured in production.

**`_preload_content=False` changes the return type and the call site mishandles it** → It returns a stream rather than a string, so the code must read and decode it. Getting this wrong yields empty logs, which is more visible than the current bug rather than less. The regression test covers it.

**Very large logs are read into memory at once** → Already true today, and `truncate_output` (`task_manager.py:2194`) bounds what is stored. Not made worse here.

**The fix looks like it did nothing** → Until the backfill runs, every existing task still displays raw, so a reviewer checking an old task after deploying sees no change. Worth stating plainly, because the natural test — open a task and look — gives a false negative on anything created before the fix.

## Migration Plan

The code fix and the backfill are independent and can land together. Order within the change: fix and test first, so the backfill is not written against a still-broken writer.

The backfill runs as an Alembic data migration. Its downgrade cannot restore the repr, and should not try — reverting to corrupt data has no value. Rollback of the code fix is a version revert; rows already repaired stay repaired and are correct under both versions.

## Open Questions

- **Should the backfill be a migration or a one-off script?** A migration runs automatically under `AUTO_MIGRATE` and is recorded, which is right for a repair everyone needs. A script keeps a one-way data rewrite out of the schema history and lets an operator choose the moment. Leaning migration, because an unrun script means the fix looks broken for every existing task.
- **How should an unrecoverable row be surfaced?** Silently skipping is safe but leaves someone puzzled later. Logging a count of skipped rows is probably enough; per-row detail could be noisy.
- ~~**Is `truncate_output` interacting with this?**~~ **Answered.** Measured against production before writing the migration: of the tasks with logs, **25 are corrupt and recoverable, 0 are truncated past their closing quote, and 2 are healthy**. So the backfill is expected to repair every affected row. The guard stays in the migration regardless — `truncate_output` bounds by encoded byte length and can produce an unterminated repr in future, and a migration that assumes otherwise would corrupt the row it could not parse.
