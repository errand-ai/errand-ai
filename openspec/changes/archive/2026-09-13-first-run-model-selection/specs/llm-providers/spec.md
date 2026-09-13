## ADDED Requirements

### Requirement: A model is never chosen by guessing

The server SHALL NOT select a model on the user's behalf except where the provider offers exactly one. Where a provider lists more than one model and the caller supplied no choice, no model setting SHALL be written.

A provider's model listing is undifferentiated. It carries no mode field, and chat, embedding, reranker and speech models arrive in one list — measured against a real runtime: `Qwen3.8-27B-MLX-4bit`, `Qwen3-Embedding-0.6B-4bit-DWQ`, `Qwen3-Reranker-4B-mxfp8`, `whisper-large-v3-turbo`. Taking the first is a guess that some orderings answer with a speech model, and the naming heuristic that would exclude the others is already rejected elsewhere in this capability because a substring check for `embed` misses `bge-m3`.

A model stored on a guess is a setting the user did not make, presented as one they did, and its failure surfaces later as a task that will not run for reasons the settings screen appears to contradict. This is the restraint already applied to credentials: no sentinel, no blank, no guess.

#### Scenario: A sole model needs no choice

- **WHEN** model settings are established for a provider whose listing contains exactly one model
- **THEN** that model is used

#### Scenario: Several models are not narrowed by name

- **WHEN** a provider lists several models and no choice was supplied
- **THEN** no model setting is written
- **AND** no model is selected by position or by name

#### Scenario: A listing that cannot be read chooses nothing

- **WHEN** a provider's model listing cannot be retrieved
- **THEN** no model setting is written

### Requirement: Scanning an installation with no model established offers to establish one

Where a scan registers a provider on an installation that has no model configured, the scan result SHALL carry what a caller needs to resolve that: which provider was registered, and whether a model is configured as of that scan. The latter SHALL be named distinctly from the configuration state a caller may read directly, because the two answer different questions and only the scan's can be undeterminable — a caller typing one from the other gets the wrong domain. Where the provider offers exactly one model, the model settings SHALL be established from it and the scan result SHALL say so.

The scan is where the question belongs. A provider has just come into existence, the user is looking at the result, and the model listing is one request away. Nowhere else in the product is the question put at all, which is why a newly installed system reaches its first task with a default provider and no usable model.

Establishing model settings SHALL apply only where no role setting has been **set**, by the same rule under which detection claims the default provider only on an empty installation: with nothing configured there is nothing to override. An installation that already has model settings SHALL keep them.

Set is a wider test than usable, deliberately, and the two must not be conflated. A model named with no provider is the legacy shape — a bare model name resolving against the default base URL with a key from credentials — and tasks still run on it; a model naming a provider that has since been deleted does not resolve at all. Neither is reported as configured, because neither can serve every role. But both were chosen by somebody, and a scan is not the moment to decide that choice was wrong: replacing them would take a running installation off the model its operator picked, on the strength of a button they pressed to look for local runtimes.

#### Scenario: A model setting that does not resolve is still not replaced

- **WHEN** a scan would establish a sole model on an installation whose role setting names a model with no provider, or a provider that no longer exists
- **THEN** no model setting is established
- **AND** the existing setting is unchanged

#### Scenario: A scan on an empty installation reports that no model is configured

- **WHEN** a scan registers a provider on an installation with no model configured
- **THEN** the result identifies the provider the scan registered, and reports that no model is configured
- **AND** where another provider holds the default, it is not the one identified

#### Scenario: A sole model is established by the scan

- **WHEN** a scan registers a provider that offers exactly one model on an installation with no model configured
- **THEN** the model settings are established from it
- **AND** the result reports that a model was established, and which one

#### Scenario: Existing model settings are not replaced

- **WHEN** a scan registers a provider on an installation that already has a model configured
- **THEN** the existing model settings are unchanged
- **AND** the result does not report a missing model

### Requirement: A model can be chosen for a detected provider

The server SHALL accept a caller-supplied choice of provider and model and establish it as the model settings that govern task classification and task execution. The choice SHALL be rejected where the named provider does not exist, and where the named model is not one the provider lists.

The set of roles a single choice governs SHALL be exactly the model settings a task needs to run and to be classified. Growing that set is a change to what a caller's users were told they were agreeing to: consumers disclose what the one answer covers, so a role added here silently makes their wording false. Any addition therefore requires the consumers to be told, not merely the server to be changed.

The model SHALL be nameable as either `model` or `model_id`. `model` is canonical, and `model_id` is what the shared settings card writes; the existing setting resolution already accepts either, and an operation accepting only one would leave a client using both names for one concept in two calls, with a translation between them. That translation is where a mismatch hides — reading only `model` in one place reported a card-configured installation as having no model, after which a scan would have overwritten the user's own choice.

It SHALL be a single operation, not a write of individual settings keys. A caller states which model errand should use; which settings implement that, and how many there are, is the server's business. Expressing the choice as a settings write would put the current set of roles into every caller, so adding or renaming one later would silently leave callers configuring a subset — which is this change's own defect, reintroduced by the fix for it. A single operation also lets the model be validated against the provider's listing, which a generic settings write cannot do.

Validating the model against the listing is what separates a choice from a typo. A setting naming a model the provider does not serve produces a task that fails at the point of use, far from the screen where the mistake was made.

#### Scenario: Either name for the model is accepted

- **WHEN** a caller names the model as `model`, or as `model_id`
- **THEN** the choice is established in both cases
- **AND** supplying neither is rejected

#### Scenario: A chosen model is established

- **WHEN** a caller supplies a provider and one of the models it lists
- **THEN** the model settings governing classification and execution are set to that provider and model
- **AND** the caller does not name the individual settings being written

#### Scenario: A model the provider does not serve is refused

- **WHEN** a caller supplies a model the named provider does not list
- **THEN** the choice is refused and no setting is changed

#### Scenario: A provider that does not exist is refused

- **WHEN** a caller supplies a provider that does not exist
- **THEN** the choice is refused and no setting is changed

### Requirement: Whether a model is configured is reported, not inferred

The server SHALL expose whether a usable model is configured, and SHALL do so where a caller managing providers already looks — readable without running a scan. A caller SHALL NOT have to read the model settings and compare them against the provider list to determine it.

A scan is a deliberate, side-effecting action that reconciles providers; requiring one to discover a state that is true on arrival would mean a caller either cannot render the state on load, or runs a reconciliation to ask a question.

Today the absence has no representation: the settings hold `{"provider_id": null, "model": ""}`, which is indistinguishable from a value never set, and the only visible consequence is a task that behaves unexpectedly. A state that governs whether the product works at all should be answerable directly.

A model setting naming a provider that no longer exists SHALL be reported as not configured, because it cannot be used.

#### Scenario: An unconfigured installation says so

- **WHEN** no model setting has been established
- **THEN** the server reports that no model is configured

#### Scenario: The state is available without scanning

- **WHEN** a caller reads the configured providers without running a scan
- **THEN** whether a model is configured is available to it

#### Scenario: A configured installation says so

- **WHEN** a model setting names an existing provider and a model it lists
- **THEN** the server reports that a model is configured

#### Scenario: A setting pointing at a departed provider is not configured

- **WHEN** a model setting names a provider that no longer exists
- **THEN** the server reports that no model is configured
