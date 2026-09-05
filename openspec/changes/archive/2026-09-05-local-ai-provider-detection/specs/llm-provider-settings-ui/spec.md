## ADDED Requirements

### Requirement: Providers are added by choosing from a catalog

The provider settings UI SHALL offer a list of known providers to choose from when adding a provider, rather than requiring a base URL to be typed. Choosing a listed provider SHALL require only an API key. The list SHALL include an explicit entry for an unlisted OpenAI-compatible provider.

#### Scenario: Adding a listed provider

- **WHEN** the user adds a provider and selects a listed entry
- **THEN** only an API key is requested
- **AND** the base URL is taken from the catalog entry

#### Scenario: Adding an unlisted provider

- **WHEN** the user selects the unlisted OpenAI-compatible entry
- **THEN** fields for a base URL and an API key are revealed
- **AND** both are required before the provider can be saved

#### Scenario: Key acquisition is signposted

- **WHEN** a listed provider is selected
- **THEN** the UI links to where that provider's API key is obtained

### Requirement: Model browsing adapts to model-listing support

The provider settings UI SHALL let a user find out which models a configured provider offers. Where the provider supports model listing, the retrieved models SHALL be presented. Where it declares no model-listing support, or listing fails, the UI SHALL accept a directly entered model name so that the user can still establish a usable name, rather than being left with nothing.

This control browses; it does not store a selection. `llm_providers` has no model column and nothing persists a model against a provider — per-role model choices are saved by the LLM models settings card, against the `llm_model`, `task_processing_model` and `transcription_model` settings. The question this control answers is "what may I name for this provider?", and no more.

#### Scenario: Provider supports listing

- **WHEN** a provider that supports model listing is configured
- **THEN** its models are presented

#### Scenario: Provider does not support listing

- **WHEN** the selected provider declares no model-listing support
- **THEN** a model name can be entered directly

#### Scenario: Listing fails at runtime

- **WHEN** model listing is attempted and fails
- **THEN** the UI offers direct entry and explains why the list is unavailable
- **AND** does not leave the control looking as though it is still loading

#### Scenario: Long model lists remain usable

- **WHEN** a provider returns a large number of models
- **THEN** the selection control supports filtering by typing rather than requiring scrolling through the whole list

### Requirement: Local AI runtimes can be discovered from the UI

The provider settings UI SHALL offer a control that scans for local AI runtimes and presents what was found for the user to adopt. Where detection is unavailable for the deployment, the control SHALL explain that rather than appearing broken.

#### Scenario: Scan finds runtimes

- **WHEN** the user runs a scan and local runtimes are found
- **THEN** they are presented with their name and endpoint

#### Scenario: Scan finds nothing

- **WHEN** the user runs a scan and nothing responds
- **THEN** the UI reports that no local AI was found, without presenting an error

#### Scenario: Detection unavailable

- **WHEN** the deployment cannot reach a container host
- **THEN** the scan control explains that local detection is not available for this deployment

### Requirement: Provider reachability is visible

The provider settings UI SHALL show whether each configured provider is currently reachable, and SHALL offer a way to re-check. A provider whose backing service has stopped SHALL be visibly distinguishable from a working one.

#### Scenario: Unreachable provider is marked

- **WHEN** a configured provider's service is not responding
- **THEN** the UI shows it as unreachable

#### Scenario: Re-check available

- **WHEN** the user re-checks a provider
- **THEN** its reachability state is refreshed
- **AND** its stored configuration is unchanged

### Requirement: Detected providers are identified as such

Providers created by local detection SHALL be visibly distinguished from manually configured ones, and the UI SHALL indicate that they are reconciled by scanning rather than edited by hand.

#### Scenario: Detected provider labelled

- **WHEN** a detected provider is listed
- **THEN** it is shown as detected rather than as a manually configured provider
