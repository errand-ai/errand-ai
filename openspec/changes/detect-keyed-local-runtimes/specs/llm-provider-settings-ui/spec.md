## ADDED Requirements

### Requirement: Scan results offer to adopt a runtime that needs a key

Where a scan reports a local AI runtime requiring an API key, the provider settings UI SHALL present it alongside the runtimes that were registered, distinguished as needing credentials, and SHALL offer a field to supply a key and adopt it.

A runtime needing a key SHALL NOT be presented as an error, and SHALL NOT be presented in a way that suggests nothing was found.

#### Scenario: Keyed runtime presented for adoption

- **WHEN** a scan reports a runtime requiring an API key
- **THEN** it is shown with its endpoint, marked as needing a key
- **AND** a field is offered to supply one

#### Scenario: Adopting with a key

- **WHEN** the user supplies a key for a reported runtime and adopts it
- **THEN** the provider list refreshes to include it
- **AND** it is no longer listed as needing a key

#### Scenario: A rejected key is explained

- **WHEN** the supplied key is rejected by the runtime
- **THEN** the UI says the key was not accepted
- **AND** the runtime remains available to try again

#### Scenario: Registered and key-requiring runtimes are both shown

- **WHEN** a scan finds one runtime needing no key and another needing one
- **THEN** both are presented, distinguished from each other
