## 1. Branch and sequencing

- [x] 1.1 Create branch `reduce-compaction-recomputation`
- [ ] 1.2 Bump `VERSION` (minor — behaviour change to compaction)
- [ ] 1.3 Settle the order against `pin-constraints-across-compaction` and record it in both changes. Both edit the split in `_compact_context` — that one excludes `messages[0]` from summarisation, this one constrains where the boundary may fall. Compatible in principle, conflicting if developed in parallel
- [x] 1.4 Note the branch dependency: this branch is cut from `pin-constraints-across-compaction`, because the archive/sync of `fix-context-compaction` lives there and `main`'s specs are stale without it. Either merge that first, or rebase this onto `main` once it lands — **resolved**: PR #236 merged as `dff635e` (squash), carrying both the `fix-context-compaction` archive and the `pin-constraints-across-compaction` artifacts. This branch was reconstructed from `main` (the squash made a plain rebase replay commits already present). `main`'s `task-runner-context-compaction` spec now holds all 8 synced requirements, so this change's `MODIFIED` delta targets live text

## 2. Split-point safety — do this first

The only item here that can fail a live task rather than merely cost time. Independent of everything else, so it should not wait on the riskier work below.

- [ ] 2.1 Write failing tests first: a boundary falling between a `function_call` and its `function_call_output` is moved; the retained portion never begins with an orphaned output; a boundary already at a safe point is left unchanged
- [ ] 2.2 Write a failing test for the degenerate case — moving forward past a very large tool pair retains less than `KEEP_RECENT_TOKENS`, and compaction proceeds anyway
- [ ] 2.3 Move the boundary **forward**, not backward. Forward cuts deeper; backward retains a larger tail and can leave the conversation still over the limit after a compaction that reported success — a silent failure rather than a lossy one
- [ ] 2.4 Confirm this composes with the existing "at least one summarised, at least one kept" clamp
- [ ] 2.5 Consider whether to ship this alone, ahead of the rest. Four independent implementations guard this and errand does not; the fix is small and the rest of this change is not

## 3. Summary state

- [ ] 3.1 Write failing tests first: a held summary matching the messages triggers the merge prompt; only messages beyond the covered prefix are sent; a content mismatch falls back to a full summarisation; no held summary falls back to a full summarisation
- [ ] 3.2 Write a failing test that the held summary is cleared on agent retry, as `_compaction_backoff` is
- [ ] 3.3 Add the summary record alongside `_compaction_backoff` — summary text plus a digest of exactly what it covered — with the same per-attempt reset
- [ ] 3.4 Key the record on **content**, not index or message count. Indices shift as the SDK rebuilds the list between turns and a count establishes nothing about identity. This is the change's main hazard: a stale summary spliced in front of unrelated messages misrepresents history with no error raised
- [ ] 3.5 Fall back to full summarisation on any doubt — mismatch, missing record, post-reset. An unnecessary full pass costs 30 seconds; a wrong merge costs correctness

## 4. Make the merge path live

- [ ] 4.1 Route to `MERGE_COMPACTION_PROMPT` when a held summary matches, using the existing `_is_compaction_summary` logic only where it still applies
- [ ] 4.2 Treat `MERGE_COMPACTION_PROMPT` as **unproven code**. It is specified and unit-tested against synthetic input but has never executed in production, because the marker it depends on is never present. Review and test it as new, not as existing behaviour
- [ ] 4.3 Confirm the file-operation tracking requirement still holds across a merge — `File operation tracking across compactions` specifies that merged summaries carry file lists from both sides

## 5. Observability

- [ ] 5.1 Log merge-versus-full at `WARNING`, so whether chaining engaged is readable rather than inferred from call timings
- [ ] 5.2 Write a test that both lines survive a `WARNING`-configured runner

## 6. Verify

- [ ] 6.1 Full task-runner suite green
- [ ] 6.2 Drive two compactions in one run and confirm the second is a merge, sending only the new messages
- [ ] 6.3 Confirm a mismatch genuinely falls back rather than merging anyway — the failure this design fears most is the one that raises no error
- [ ] 6.4 Deploy and confirm via Loki: `{app="task-runner"} |= "Context compaction"` should show one full summarisation followed by merges, where the baseline showed four full summarisations in 104 seconds each re-covering the same 49 messages

## 7. Ship

- [ ] 7.1 Commit, push, open a PR
- [ ] 7.2 CI green
- [ ] 7.3 Deploy and run 6.4 against the deployment
- [ ] 7.4 Merge, delete branch
- [ ] 7.5 Archive the change so its deltas reach `openspec/specs/` — `fix-context-compaction` was merged without archiving and left the main specs stale for a day

## 8. Deliberately not addressed

- [ ] 8.1 Making compaction persist across turns. The SDK does not support it: `call_model_input_filter` is per-call by construction, sessions are read once before the turn loop, and maintainers have declined to add a provider-agnostic equivalent (issue #2671 remains open)
- [ ] 8.2 The overflow-retry architecture (strix, koder, Datus) — compact between runs and restart `Runner` with the compacted history. The only approach that genuinely persists, and errand is closer to it than expected since it already retries around `Runner.run_streamed()`. Its own change
- [ ] 8.3 Evicting reconstructible tool outputs before summarising — the Manus tiering, and `agents.extensions.ToolOutputTrimmer` (undocumented, provider-agnostic). Probably higher value than anything here, since errand's context is dominated by large file reads. Its own change
- [ ] 8.4 Changing `KEEP_RECENT_TOKENS`. Settled: 20,000 is the convergent constant across Cline and Codex
- [ ] 8.5 A forced full re-summarisation every N merges, to bound drift. No published guidance found on where that threshold should sit; add a generation counter if quality degradation is observed
