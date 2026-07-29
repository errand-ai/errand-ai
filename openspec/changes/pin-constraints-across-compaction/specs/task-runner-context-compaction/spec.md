## ADDED Requirements

### Requirement: The initial task prompt survives compaction

Compaction SHALL NOT summarise the first message of the conversation. The first message SHALL be carried through verbatim, ahead of the generated summary, regardless of its size.

This matches the guarantee trimming already makes — `agent-context-management` requires that "the first message (initial user prompt) is always retained regardless of its size" — so the two context-management paths agree about whether the user's instructions are load-bearing.

The first message contains the task's own instructions, including any prohibitions and scope limits. Summarising it makes their survival depend on what the summariser chose to keep, on tasks that run unattended and whose tools post to Slack, send mail, write to cloud storage and push to git.

Preserving the message verbatim SHALL be preferred over extracting and re-injecting constraint text. Extraction requires deciding which text is a constraint, and a rule that misses one is worse than none, because it creates confidence that constraints are protected when they are not.

#### Scenario: First message is not summarised

- **WHEN** compaction runs on a conversation of many messages
- **THEN** the first message is not part of the summarised portion

#### Scenario: First message is present verbatim after compaction

- **WHEN** compaction completes
- **THEN** the resulting message list begins with the original first message, byte-identical to the input

#### Scenario: Summary follows the preserved prompt

- **WHEN** compaction completes
- **THEN** the generated summary appears after the preserved first message, not in place of it

#### Scenario: Large first message is still preserved

- **WHEN** the first message is large enough that preserving it consumes a significant share of the budget
- **THEN** it is preserved in full and not truncated

#### Scenario: A compaction summary at the first position is not preserved
- **WHEN** the first message is itself a compaction summary rather than an initial prompt
- **THEN** it SHALL NOT be preserved verbatim, and SHALL remain eligible for merging

Preserving it would pin a summary permanently and stop it ever being updated, which is worse than not preserving. A summary in that position means the original prompt was already summarised away, so there is nothing left to protect.

#### Scenario: Consistency with trimming

- **WHEN** the same conversation is trimmed instead of compacted
- **THEN** the first message is preserved by both paths

### Requirement: Compaction summaries carry constraints forward

The summarisation prompt SHALL instruct the model to record constraints — prohibitions, approval requirements, and scope limits — and to carry them forward in their original wording rather than paraphrased.

Preserving the first message protects constraints that arrived with the task. It does not protect constraints that arrive later: a skill read mid-task, a policy in a tool result, or a follow-up instruction. Those are summarised, so the summary must be biased toward retaining them.

#### Scenario: Constraint stated mid-task is carried forward

- **WHEN** a constraint appears in the conversation after the first message and that portion is summarised
- **THEN** the summarisation prompt directs the model to record it among the constraints

#### Scenario: Constraints are not paraphrased

- **WHEN** the summary records a constraint
- **THEN** the prompt directs that its original wording be retained rather than reworded

#### Scenario: No constraints present

- **WHEN** the summarised portion contains no constraints
- **THEN** the summary is produced normally with that section empty

### Requirement: Prompt preservation is observable

When compaction preserves the first message, the task runner SHALL log that it did so, and the size preserved, at `WARNING` or above.

Production runs the task runner above `INFO`, so a lower level would make this invisible in the deployment where it matters. Recording it means a task that somehow lost its instructions is detectable after the fact rather than inferred from behaviour.

#### Scenario: Preservation is logged at the production level

- **WHEN** compaction preserves the first message and the runner is configured at `WARNING`
- **THEN** a log line reporting the preservation and its size is emitted
