## MODIFIED Requirements

### Requirement: Step 3 — Model selection

The third wizard step SHALL present a single model choice, populated from `GET /api/llm/providers/{id}/models` using the provider ID from Step 2. No model SHALL be selected on the user's behalf except where the provider lists exactly one, in which case that one SHALL be selected. Leaving the choice unmade SHALL be permitted and SHALL write nothing.

The step previously offered a dropdown per role, each defaulting to a named Anthropic model. A user setting up against a local runtime and touching neither dropdown had a model written against a provider that has never served it: every task then failed while the settings reported a model was configured. A default is not a neutral starting point when it names a specific vendor's model on an installation configured for a different provider.

A "Complete Setup" button SHALL apply the choice through the single model-selection operation, naming the provider and the model, and SHALL NOT write the individual settings keys. The wizard therefore does not name the roles a choice governs; which settings implement it, and how many there are, is the server's business. Writing the keys directly also bypasses validating the model against the provider's listing, which is what separates a choice from a typo.

Where the operation is refused, the step SHALL show the reason the server gave and SHALL keep the choice available to try again. A refusal here is specific — the provider is gone, or does not serve that model, or its listing could not be read — and a generic failure message would withhold the one sentence that says what to do about it.

One answer governs both the running of tasks and the classification of new ones, so the step SHALL say so. A question that decides more than it appears to is the same fault as choosing a model on the user's behalf, arrived at from the other side; stating it is also what tells the user the two roles can later be set separately, which this step deliberately does not offer.

#### Scenario: Models populated from provider

- **WHEN** the user reaches Step 3 after a successful connection test
- **THEN** the model choice shows the models available from `GET /api/llm/providers/{id}/models`
- **AND** no model is selected unless the provider listed exactly one

#### Scenario: Setup completed with provider-aware model settings

- **WHEN** the user selects a model and clicks "Complete Setup"
- **THEN** the choice is applied through the model-selection operation, naming the provider and the model
- **AND** no individual model settings keys are written by the wizard
- **AND** the user is redirected to `/settings`

#### Scenario: No model chosen writes nothing

- **WHEN** the user completes setup without choosing a model
- **THEN** no model selection is applied and no model setting is written
- **AND** setup completes

#### Scenario: A refused choice states why and stays open

- **WHEN** applying the chosen model is refused
- **THEN** the reason given by the server is shown
- **AND** the choice remains available to try again

#### Scenario: What the choice governs is disclosed

- **WHEN** the model choice is presented
- **THEN** the step states that the answer governs both the running of tasks and the classification of new ones
