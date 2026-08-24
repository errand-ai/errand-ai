## ADDED Requirements

### Requirement: Exact per-turn context measurement

The task runner SHALL emit an `llm_turn_end` event when a model call completes, carrying the `turn_id` assigned at turn start, the exact prompt size reported by the provider, the output token count, cached-token details when the provider supplies them, and the wall-clock duration of the turn.

Token counts SHALL be taken from the model response's usage, not from the internal character-ratio estimate. The estimate exists to drive compaction and is not accurate enough to report: reporting it would place a number on screen that disagrees with the provider's own accounting.

Turn duration SHALL be reported alongside the token counts. Context size alone does not explain a slow task, because every turn re-prefills the entire context and latency therefore scales with it.

#### Scenario: Turn end reports exact usage

- **WHEN** a model call completes with a provider-reported prompt size of 38,204 tokens
- **THEN** an `llm_turn_end` event is emitted with `input_tokens` of 38204

#### Scenario: Turn end pairs with turn start

- **WHEN** a turn completes
- **THEN** the `llm_turn_end` event carries the same `turn_id` as the `llm_turn_start` event that preceded it

#### Scenario: Duration reported

- **WHEN** a turn takes 41 seconds
- **THEN** the `llm_turn_end` event reports a duration corresponding to that elapsed time

The task runner SHALL request usage reporting from the provider. Streaming providers send a usage chunk only when asked, and the agent SDK asks by default solely when the client points at OpenAI's own endpoint, so a proxied provider otherwise reports nothing.

#### Scenario: Missing usage does not break the turn

- **WHEN** a provider returns a response without usage information
- **THEN** the task runner SHALL still complete the turn, omitting the token fields rather than failing

#### Scenario: A usage report of zeros is not a measurement

- **WHEN** a provider returns a usage block whose prompt size is zero
- **THEN** the token fields SHALL be omitted rather than reported as zero

No real turn has an empty prompt, so a zero is the provider declining to answer. Reporting it would put a confidently wrong number on screen, which is the outcome measuring rather than estimating exists to avoid.

### Requirement: The context ceiling is resolved rather than assumed

The ceiling that compaction fires at, and that pressure thresholds are measured against, SHALL be configurable and SHALL be passed to the task runner. When no value is configured the runner SHALL keep its own default.

The percentage in a pressure event is meaningless without a stated denominator, and a ceiling hard-coded in the runner cannot be corrected for a deployment whose models want a different one.

#### Scenario: Configured ceiling reaches the runner

- **WHEN** a context ceiling of 90,000 is configured
- **THEN** the task runner receives that value and measures pressure against it

#### Scenario: Unconfigured ceiling leaves the runner's default intact

- **WHEN** no context ceiling is configured
- **THEN** no ceiling is passed and the task runner applies its own default

#### Scenario: Pressure events state the ceiling they used

- **WHEN** a `context_pressure` event is emitted
- **THEN** it carries the ceiling the measurement was compared against

### Requirement: Context pressure is signalled at thresholds

The task runner SHALL emit a `context_pressure` event when the measured context crosses a pressure threshold, and SHALL NOT emit one on turns that cross no threshold. The event SHALL carry the measured token count, the ceiling it is measured against, and the threshold crossed.

Continuous per-turn warnings would be noise; the operator needs to know when the situation changes, not that it persists.

#### Scenario: Crossing a threshold signals once

- **WHEN** the context crosses a pressure threshold on a given turn
- **THEN** exactly one `context_pressure` event is emitted for that crossing

#### Scenario: Remaining above a threshold does not re-signal

- **WHEN** the context is above a threshold it has already crossed and crosses no further threshold
- **THEN** no additional `context_pressure` event is emitted

#### Scenario: Below all thresholds is silent

- **WHEN** the context is comfortably below every threshold
- **THEN** no `context_pressure` event is emitted

### Requirement: Diagnostic snapshots record what filled the context

On significant events only — compaction triggered, compaction failed, or a pressure threshold crossed — the task runner SHALL emit a `context_snapshot` event carrying the measured token count, the message count, and the largest contributors to the context.

Contributors SHALL be identified by role, tool name and size. Snapshots SHALL NOT carry message content. The diagnostic question is which inputs consumed the window, which names and sizes answer; including content would add nothing and would place task data into log retention.

Snapshots SHALL NOT be emitted per turn. Their value is in explaining a significant event, and per-turn emission would make them routine noise in a channel intended for the exceptional.

#### Scenario: Snapshot on compaction

- **WHEN** compaction is triggered
- **THEN** a `context_snapshot` event is emitted reporting the token count, message count and largest contributors

#### Scenario: Contributors identify the source without the content

- **WHEN** a single tool result of 62,331 characters is the largest contributor
- **THEN** the snapshot reports that tool's name and size, and does not include its output

#### Scenario: Ordinary turns produce no snapshot

- **WHEN** a turn completes without triggering compaction or crossing a threshold
- **THEN** no `context_snapshot` event is emitted

### Requirement: Context usage is visible on the turn separator

The task log view SHALL display the measured context usage for a turn on that turn's separator, alongside the model name it already shows. The display SHALL include the absolute token count, not only a percentage, so the raw figure remains visible when the percentage's denominator is not the constraint that matters.

Because usage is only known once the model call returns, the separator SHALL render before its usage is available and SHALL populate the value on arrival, in the same manner as the existing thinking placeholder.

#### Scenario: Usage shown once known

- **WHEN** an `llm_turn_end` event arrives for a rendered turn
- **THEN** that turn's separator displays the context usage for the turn

#### Scenario: Separator renders before usage arrives

- **WHEN** a turn has started but its model call has not returned
- **THEN** the separator renders with the model name and without a usage figure, and does not display a placeholder number

#### Scenario: Absolute count shown alongside any percentage

- **WHEN** usage is displayed
- **THEN** the absolute token count is shown, not a percentage alone

#### Scenario: Turns without usage render unchanged

- **WHEN** no `llm_turn_end` event is received for a turn
- **THEN** the separator renders as it does today, with no usage figure and no error
