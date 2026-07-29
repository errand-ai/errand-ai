## 1. Branch and version

- [x] 1.1 Create branch `pin-constraints-across-compaction` from an up-to-date `main`
- [ ] 1.2 Bump `VERSION` (minor — behaviour change to what survives compaction)

## 2. Sequence against the other compaction change

Both this and `reduce-compaction-recomputation` edit the split in `_compact_context`. Settle the order before writing code, not after.

- [x] 2.1 Decide which of the two lands first and record it in both changes. They are compatible in principle — one constrains where the split may fall (never between a `function_call` and its `function_call_output`), the other what is excluded from summarisation (`messages[0]`) — but developed blind to each other they will conflict — **decided: `reduce-compaction-recomputation` lands first.** Its split-point bug can orphan a tool call from its result and fail a live task; this change costs safety margin but is not actively breaking runs. Recorded in that change's `tasks.md` §1.3
- [ ] 2.2 If this one lands second, rebase onto the other before starting — **this one lands second**, so rebase onto `main` after `reduce-compaction-recomputation` merges. Expect to touch the same lines: that change snaps `split_idx` forward to a tool-pair boundary, this one reserves `messages[0]` from the summarised portion. Both operate on `split_idx`, so reconcile rather than reapply

## 3. Preserve the initial task prompt

The structural fix, and the whole reason this change exists.

- [ ] 3.1 Write failing tests first: after compaction the first message is present and byte-identical to the input; it is not part of the summarised portion; the summary appears after it
- [ ] 3.2 Write a failing test that a large first message is preserved in full rather than truncated — truncating a constraint mid-sentence is the exact failure this change prevents
- [ ] 3.3 Write a test asserting trimming and compaction agree: the same conversation through either path retains the first message
- [ ] 3.4 Exclude `messages[0]` from the summarised portion and carry it through ahead of the summary
- [ ] 3.5 Confirm this composes with the existing "at least one message summarised, at least one kept" clamp — with the first message reserved, the clamp's bounds change
- [ ] 3.6 Confirm no double-counting: the preserved message must not also appear inside the summary's source text

## 4. Carry later constraints through the summary

Covers what the structural fix cannot: constraints arriving mid-task from a skill, a tool result, or a follow-up.

- [ ] 4.1 Add a constraints section to `FIRST_COMPACTION_PROMPT` and `MERGE_COMPACTION_PROMPT`, instructing that prohibitions, approval requirements and scope limits are recorded in their original wording rather than paraphrased
- [ ] 4.2 Write a test that both prompts contain the instruction — the prompt text is the deliverable here, since the model's compliance cannot be unit-tested
- [ ] 4.3 Confirm a summarised portion containing no constraints still produces a normal summary
- [ ] 4.4 Check the added section against the token budget — it takes space from Progress and Key Decisions, which is a real trade rather than a free addition

## 5. Observability

- [ ] 5.1 Log preservation and the size preserved at `WARNING` — production runs above `INFO`, so anything lower is invisible where it matters
- [ ] 5.2 Write a test that the line survives a `WARNING`-configured runner

## 6. Verify

- [ ] 6.1 Task-runner suite green
- [ ] 6.2 Structural check, which IS unit-testable: drive a conversation past the threshold and assert `messages[0]` is present and unmodified afterwards
- [ ] 6.3 Empirical check, which is not: run a task whose prompt carries an explicit prohibition, past the compaction threshold, and inspect the post-compaction context for the instruction. The GetBookable review shape works — it compacted four times and its prompt said "Do not open pull requests, push commits, or modify the repository"
- [ ] 6.4 Confirm via Loki that the preservation line appears, using the same `{app="task-runner"} |= "Context compaction"` query that confirmed `fix-context-compaction`

## 7. Ship

- [ ] 7.1 Commit, push, open a PR
- [ ] 7.2 CI green
- [ ] 7.3 Deploy and run 6.3 against the deployment
- [ ] 7.4 Merge, delete branch
- [ ] 7.5 Archive the change so its deltas reach `openspec/specs/` — `fix-context-compaction` was merged without archiving and left the main specs stale for a day

## 8. Deliberately not addressed

- [ ] 8.1 Skill content reaching the model as tool results, and therefore being compactable. A real gap, but fixing it changes how skills are delivered. Audit the system skills first (open question in design): if they are purely procedural this is low priority; if any carry load-bearing constraints it is not
- [ ] 8.2 Enforcing constraints. This change is about survival only — nothing checks what the model does afterwards
- [ ] 8.3 Adversarial hardening against the Compaction-Eviction Attack. Preserving the prompt verbatim removes the summariser's discretion over that text, which addresses the mechanism, but is not a robustness claim
- [ ] 8.4 A structured constraints field on the task, so pinning is unambiguous rather than best-effort prose parsing. Larger change; noted in design
