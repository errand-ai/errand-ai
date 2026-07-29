## Why

Compaction summarises the older part of a conversation into a checkpoint. Anything the summariser omits is gone for the rest of the task — and what it omits is not chosen with safety in mind.

[Governance Decay](https://arxiv.org/abs/2606.22528) benchmarks this across 1,323 episodes with deterministic tool-call grading: the prohibited-action rate is **0% while the policy is in context and 30% on average after compaction**, rising to 59% for the worst model. Conditioned on the summary itself, it is 0% where constraints survived summarisation and 38% where they were dropped. The paper also demonstrates a Compaction-Eviction Attack: content crafted to bias the summariser into omitting legitimate policies, effective against every model tested. Their mitigation — quarantining constraints outside the compactable region — restores 0%.

errand is more exposed than a chat assistant. Tasks run unattended, and the tools have real side effects: Slack posts, Gmail sends, Google Drive and OneDrive writes, git pushes, Jira transitions. A constraint that evaporates mid-task does not produce a wrong answer for a human to catch; it produces an action.

### What is already safe

The system prompt, `FILE_TOOL_GUIDANCE`, the tool catalog and `OUTPUT_INSTRUCTIONS` are assembled into `full_instructions` and passed as the agent's `instructions`, not as messages. `filter_model_input` returns `ModelInputData(input=messages, instructions=data.model_data.instructions)` — instructions pass through untouched, so compaction cannot reach them. That is a meaningful head start and narrows this change considerably.

### What is not

**1. The initial task prompt is summarised.** The two context-management paths disagree about whether it is load-bearing:

```python
_trim_context_window:   first = messages[:1]                  # explicitly preserved
_compact_context:       to_summarize = messages[:split_idx]   # split_idx >= 1, so messages[0] is always summarised
```

`agent-context-management` even specifies the trim behaviour — *"the first message (initial user prompt) is always retained regardless of its size"* — with a scenario asserting it. Compaction has no equivalent guarantee, and the disagreement looks accidental rather than reasoned.

This is not hypothetical. The GetBookable security review run (task `8114ff66`) was given: *"Do not open pull requests, push commits, or modify the repository — this is a read-only review."* That instruction lives in `messages[0]`. The task compacted **four times**, on a clone with push access. Whether the constraint survived depended entirely on what the summariser chose to keep, and nothing checked.

**2. Skill instructions arrive as tool results.** System and user skills are `SKILL.md` files the agent reads through the file tools, so their content enters context as `function_call_output` items — squarely inside the compactable region. A skill saying "always ask before sending" is exactly the kind of prose a summariser compresses to "reviewed the skill instructions".

**3. Nothing verifies constraint survival.** The summarisation prompt asks for Goal / Progress / Key Decisions / Next Steps / Files. No section is reserved for constraints, and no check confirms one survived.

## What Changes

- **Preserve the initial task prompt across compaction**, matching the guarantee trimming already makes. The cheapest and highest-value item: it is one message, it contains the user's actual instructions, and the inconsistency with trimming is almost certainly unintended.
- **Add a constraints section to the summarisation prompt**, instructed to carry forward prohibitions, approval requirements and scope limits verbatim rather than paraphrased. Anthropic's guidance for compaction prompts is to *maximise recall first, then improve precision* — constraints are the clearest case for recall.
- **Re-inject pinned constraint text after compaction** rather than trusting the summary to have retained it, so survival does not depend on model behaviour. This is the mitigation the paper validates.
- **Log which constraints were pinned** at `WARNING`, so a task that silently lost one is visible — consistent with the lifecycle logging added in `fix-context-compaction`.

**Not in scope:**

- Moving skill content out of tool results into `instructions`. That would protect it properly, but changes how skills are delivered and interacts with the skill-loading design; worth its own change.
- Defending against the Compaction-Eviction Attack specifically. Re-injection makes the summariser's choices non-load-bearing, which addresses it structurally, but adversarial hardening is a separate exercise.
- Changing what the tools are permitted to do. This change is about constraints surviving; it does not add enforcement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-runner-context-compaction`: preserve the initial prompt; carry constraints through summarisation; re-inject pinned text post-compaction.
- `agent-context-management`: state the initial-prompt guarantee once, so trimming and compaction stop disagreeing.

## Impact

- **Code**: `task-runner/main.py` — `_compact_context` split selection and the post-compaction message assembly, plus the summarisation prompts.
- **Interaction with `reduce-compaction-recomputation`**: both change `_compact_context`'s split. That change fixes the split orphaning a `function_call` from its `function_call_output`; this one keeps `messages[0]` out of the summarised portion. They should land in a deliberate order or be reconciled, not developed blind to each other.
- **Cost**: re-injected constraint text is re-sent every turn after a compaction. That is the point — it is the same trade the `instructions` field already makes — but it consumes budget in exactly the situation where budget is short. Pinned text should be constraints, not the whole prompt, and the size wants a bound.
- **Risk of over-pinning**: pin too much and compaction stops reclaiming enough, re-triggering sooner. Given compaction currently recomputes every turn, that cost is real until `reduce-compaction-recomputation` lands.
- **Verification is genuinely hard.** "The constraint survived" is not something a unit test settles convincingly. The honest check is a task whose prompt contains a prohibition, driven past the compaction threshold, with the post-compaction context inspected for the constraint — closer to the empirical runs used to confirm `fix-context-compaction` than to a test assertion.
