## ADDED Requirements

### Requirement: Title generation reports why it failed

`generate_title` SHALL report, alongside its success flag, whether the classification was attempted. A result that was never attempted — because no model is configured, or the configured provider no longer exists — SHALL be distinguishable from one where the request was made and did not yield a usable answer.

The two are different facts about different parties. A classifier that ran and could not extract a description has told the caller something about the input; a classifier that was never reached has told it something about the installation. Both currently arrive as `success=False`, which is why the caller cannot avoid blaming the user for an unconfigured system.

The distinction SHALL be carried in the result rather than inferred by the caller re-reading the setting. A caller that re-derives it races the state it is describing, and duplicates the resolution rule the function already applied.

The fallback title behaviour is unchanged: whatever the cause, an unusable result SHALL yield the fallback title rather than an error.

#### Scenario: No model configured is reported as not attempted

- **WHEN** title generation runs while no model is configured
- **THEN** the result reports failure
- **AND** the result reports that no attempt was made
- **AND** the fallback title is used

#### Scenario: A missing provider is reported as not attempted

- **WHEN** the configured model names a provider that no longer exists
- **THEN** the result reports that no attempt was made

#### Scenario: A completed request that yields nothing usable is reported as attempted

- **WHEN** title generation reaches the model and the response carries no usable content
- **THEN** the result reports failure
- **AND** the result reports that an attempt was made

#### Scenario: A successful call reports success

- **WHEN** title generation reaches the model and the response is usable
- **THEN** the result reports success
- **AND** the caller can rely on the existing title, category and description fields
