## ADDED Requirements

### Requirement: A scan that registers the first provider asks which model to use

Where a scan reports that a provider was registered and no model is configured, the provider settings UI SHALL present that provider's models and offer to apply a choice. The choice SHALL be applied without the user navigating elsewhere.

This is the only moment in the product where the question is cheap. The user has pressed a button and is looking at its result; a provider exists; its models are one request away. Left unasked, the next thing that happens is a task that does not run, on a screen that shows a healthy default provider.

Where the scan reports that a model was established automatically, the UI SHALL NOT ask, and SHALL say which model is in use so that a choice made on the user's behalf is visible rather than silent.

A single answer sets the model for more than one role — task execution and the classification of new tasks — so the UI SHALL say so at the point of asking. One question that quietly decides two things is the same fault as picking a model on the user's behalf, arrived at from the other direction: the user is told they are answering a smaller question than they are. Stating it also tells them where to go when they later want the two to differ, which this flow deliberately does not offer.

#### Scenario: Registered provider with no model prompts for one

- **WHEN** a scan registers a provider and reports that no model is configured
- **THEN** the provider's models are presented for selection
- **AND** choosing one applies it without leaving the panel

#### Scenario: A model established automatically is shown, not asked

- **WHEN** a scan reports that a model was established from a provider's sole model
- **THEN** no question is asked
- **AND** the model in use is stated

#### Scenario: An installation that already has a model is not asked

- **WHEN** a scan runs on an installation that already has a model configured
- **THEN** no model question is presented

#### Scenario: What the choice governs is disclosed

- **WHEN** the model question is presented
- **THEN** it states that the answer governs both the running of tasks and the classification of new ones

#### Scenario: A rejected choice keeps the question open

- **WHEN** an attempt to apply a chosen model is refused
- **THEN** the reason is shown
- **AND** the selection remains available to try again

### Requirement: An installation with no model configured says so where providers are managed

Where no model is configured, the provider settings UI SHALL state it, and SHALL make choosing one reachable from that statement. The statement SHALL NOT be presented as an error: a provider exists and works, and what is missing is a decision nobody has been asked to make.

A user whose tasks are not running needs to be told the cause on the screen that owns it. Reporting a healthy provider list while every task fails for want of a model is the same defect as reporting that no local runtime responded when one answered but wanted a key.

#### Scenario: The missing model is stated

- **WHEN** the provider settings are shown and no model is configured
- **THEN** the UI states that no model is configured
- **AND** offers a way to choose one

#### Scenario: It is not presented as a failure

- **WHEN** the missing-model state is shown
- **THEN** it is not presented as an error condition

#### Scenario: Nothing is stated once a model is configured

- **WHEN** a model is configured
- **THEN** no missing-model statement is shown
