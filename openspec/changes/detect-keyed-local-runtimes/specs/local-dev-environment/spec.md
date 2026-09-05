## ADDED Requirements

### Requirement: The published server port is configurable

The compose environments SHALL allow the host port the errand service is published on to be overridden, defaulting to 8000 so that existing deployments are unaffected. Port 8000 is the default of a local AI runtime the scan probes, so a user running one cannot otherwise bring up the shipped compose environment beside it.

#### Scenario: Default is unchanged

- **WHEN** the compose environment is brought up with no port override
- **THEN** the errand service is published on host port 8000

#### Scenario: Port overridden

- **WHEN** the compose environment is brought up with the port override set
- **THEN** the errand service is published on that port instead

#### Scenario: Coexisting with a local runtime on 8000

- **WHEN** a local AI runtime occupies host port 8000 and the override is set
- **THEN** the compose environment starts
- **AND** the runtime remains reachable at its own port for detection
