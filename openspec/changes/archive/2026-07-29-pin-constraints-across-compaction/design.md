## Context

Compaction replaces the older part of a conversation with an LLM-generated summary. Whatever the summariser omits is gone for the remainder of the task, and nothing in the current design biases it toward keeping constraints.

Most of errand's instruction surface is already safe. `full_instructions` — the system prompt, `FILE_TOOL_GUIDANCE`, the tool catalog and `OUTPUT_INSTRUCTIONS` — is passed as the agent's `instructions`, and `filter_model_input` returns `ModelInputData(input=messages, instructions=data.model_data.instructions)` with instructions untouched. Compaction cannot reach any of it.

The exposure is the message list, and specifically its first element. The two context-management paths disagree:

```python
_trim_context_window:   first = messages[:1]                  # preserved; specified, with a scenario
_compact_context:       to_summarize = messages[:split_idx]   # split_idx >= 1, so messages[0] is summarised
```

`agent-context-management` guarantees the initial prompt survives trimming. Compaction offers no equivalent, and the difference reads as an oversight rather than a decision.

The concrete case is from this repository's own use: the GetBookable review task (`8114ff66`) was instructed *"Do not open pull requests, push commits, or modify the repository — this is a read-only review."* That text lives in `messages[0]`. The task compacted four times against a clone with push access, and the instruction's survival was entirely at the summariser's discretion.

## Goals / Non-Goals

**Goals:**

- The user's task instructions survive compaction intact, not in paraphrase.
- Trimming and compaction stop disagreeing about whether the initial prompt is load-bearing.
- The summary is biased toward retaining prohibitions and scope limits, as defence in depth.
- A task whose constraints were at risk is visible in logs.

**Non-Goals:**

- Moving skill content out of tool results. Skills reach the model as `function_call_output` items and are therefore compactable, which is a real gap — but fixing it changes how skills are delivered and belongs with the skill-loading design.
- Enforcing constraints. This change is about them surviving; it adds no checking of what the model then does.
- Adversarial hardening against the Compaction-Eviction Attack as such. Preserving the prompt verbatim makes the summariser's choices non-load-bearing for that text, which addresses the mechanism structurally, but it is not a claim of adversarial robustness.
- Classifying which parts of a prompt are "constraints".

## Decisions

**Preserve `messages[0]` verbatim rather than re-injecting extracted constraints.** The proposal listed both; preserving subsumes re-injection and is strictly better. Re-injection means deciding *what* to re-inject, which means classifying text as constraint-or-not — and a classifier that misses one is worse than nothing, because it manufactures confidence that constraints are protected. Preserving the whole first message needs no classification, cannot silently miss anything, and keeps the original wording rather than a paraphrase. The cost is that a long task description stays in context permanently, which is exactly the trade `_trim_context_window` already makes ("regardless of its size").

**Mirror the trim guarantee rather than inventing a parallel mechanism.** Compaction should keep the first message for the same reason trimming does. Framing this as consistency, not as a new safety feature, keeps the two paths from drifting apart again and makes the requirement obvious to a future reader.

**Ask the summariser for constraints as well — belt and braces.** With `messages[0]` preserved, prompt-borne constraints are already safe, so a Constraints section in the summary is redundant *for those*. It is not redundant for constraints that arrived later: a skill read mid-task, a tool result carrying a policy, a user follow-up. Anthropic's guidance for compaction prompts is to maximise recall before precision, and constraints are the clearest case. This is the cheap part of the change and covers the case the structural fix does not.

**Do not attempt to bound the pinned text.** An obvious refinement is to cap the preserved prompt and truncate beyond it. Rejected: truncating a constraint mid-sentence is the failure this change exists to prevent, and a task prompt large enough to matter is itself the problem to fix. If prompts ever grow large enough to squeeze the window, that wants solving at task creation, not by silently discarding half an instruction.

**Log what was preserved, at `WARNING`.** Consistent with the lifecycle logging synced from `fix-context-compaction`, and for the same reason: production runs above `INFO`, so anything logged lower is invisible precisely when it is needed. The line should record that the prompt was preserved and its size, so a task that somehow lost it is detectable.

## Risks / Trade-offs

**The preserved prompt consumes budget permanently** → It is re-sent on every turn after compaction, in the situation where budget is already tight. Acceptable: it is one message, trimming already makes the same trade, and the alternative is losing the task's own instructions.

**Collision with `reduce-compaction-recomputation`** → Both changes modify the split in `_compact_context`. That one prevents the boundary orphaning a `function_call` from its `function_call_output`; this one keeps `messages[0]` out of the summarised portion. They are compatible in principle — one constrains where the split may fall, the other what is excluded from summarisation — but developed blind to each other they will conflict. They need a deliberate order.

**A Constraints section may crowd out other content** → The summary has a fixed token budget. Adding a section takes space from Progress or Key Decisions. Judged worth it, but it is a real trade rather than a free addition.

**Preserving the prompt can look like the problem is solved** → It covers prompt-borne constraints only. Skill-borne and mid-task constraints remain exposed, and the non-goal above should not get lost when this ships.

**The compaction trigger can be reached too late to help** → Found while attempting 6.3, and unrelated to this change's own logic. `_estimate_tokens` is `len(json.dumps(messages)) // 3`. JSON-escaped source code tokenises closer to ~2 chars/token, so the estimate under-counts: compaction fires at an *estimated* 150,000 tokens, which for that content is nearer 225,000 real tokens. On `claude-sonnet-4-5` via Bedrock (200k window) the provider rejected the request — `litellm.ContextWindowExceededError: BedrockException: Input is too long` — **before compaction ever ran**. On that arithmetic no amount of preservation or chaining helps, because the request never reaches the model.

This makes `context-usage-visibility` a correctness change rather than an observability one: an estimate that errs low means `MAX_CONTEXT_TOKENS` does not bound what the provider actually receives. It is also the likely mechanism behind the "model gets stuck under heavy context" reports that prompted this line of work. Not in scope here, but it blocks empirical verification on any model whose real window sits near the configured limit.

**Verification is not a unit test** → "The constraint survived" is checkable structurally (is `messages[0]` still present and unmodified after compaction?) and that part is testable. Whether a *summarised* constraint survived is a model-behaviour question, only answerable empirically — the same way `fix-context-compaction` was confirmed.

## Migration Plan

No schema, settings or data change. Behaviour changes only for tasks that compact.

Rollback is a version revert; nothing persists.

Ordering against `reduce-compaction-recomputation` matters more than deployment sequencing. Whichever lands second must be rebased onto the first, because both edit the same handful of lines.

## Open Questions

- Should the same guarantee extend to a compaction summary produced earlier in the task — that is, should the summary message itself be exempt from being re-summarised? `reduce-compaction-recomputation` makes this concrete by chaining summaries, so it may answer itself there.
- Do any skills currently carry load-bearing constraints, or are they all procedural? That determines how urgent the skill-content non-goal is. Worth auditing the system skills before deciding.
- Should a task be able to declare constraints explicitly — a structured field rather than prose in the prompt — so pinning is unambiguous? Larger change, but it would make this robust rather than best-effort.
