## ADDED Requirements

### Requirement: LLM timeout input in LLM Models settings card

The "LLM Models" section on the Task Management settings sub-page SHALL display a number input labelled "LLM Timeout (seconds)" for configuring how many seconds to wait for LLM responses before timing out. The input SHALL load its current value from `GET /api/settings` (key `llm_timeout`). If no `llm_timeout` setting exists, the input SHALL default to `30`. The input SHALL have a minimum value of `1`. The timeout SHALL be saved alongside the model settings when the user clicks the existing "Save" button in the LLM Models card, sent via `PUT /api/settings` with `{"llm_timeout": <number>}`. The input SHALL be included in the dirty-tracking logic so that changing it shows the "Unsaved changes" indicator.

#### Scenario: Load default timeout

- **WHEN** the Settings page loads and no `llm_timeout` setting exists
- **THEN** the "LLM Timeout (seconds)" input displays `30`

#### Scenario: Load existing timeout

- **WHEN** the Settings page loads and `llm_timeout` is set to `60`
- **THEN** the "LLM Timeout (seconds)" input displays `60`

#### Scenario: Save timeout with model settings

- **WHEN** the admin changes the timeout to `120` and clicks "Save" in the LLM Models card
- **THEN** the frontend sends `PUT /api/settings` with `{"llm_timeout": 120}` alongside the model settings and displays a success indication

#### Scenario: Unsaved changes indicator shown

- **WHEN** the admin changes the timeout value without saving
- **THEN** the "Unsaved changes" indicator appears near the Save button

#### Scenario: Minimum value enforced

- **WHEN** the admin enters `0` in the timeout input
- **THEN** the input enforces a minimum of `1`
