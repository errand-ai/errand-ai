## MODIFIED Requirements

### Requirement: Server capability advertisement

In addition to the Wave 1 capability keys, the errand server's `/api/capabilities` endpoint SHALL advertise the following Wave 2 keys:

- `llm_providers` — always advertised
- `llm_models` — always advertised
- `google_workspace` — advertised when the Google Workspace integration is enabled (existing runtime detection)
- `platforms` — always advertised
- `task_profiles` — always advertised

#### Scenario: Wave 2 always-on keys advertised
- **WHEN** any client requests `GET /api/capabilities`
- **THEN** the response `capabilities` array SHALL include `"llm_providers"`, `"llm_models"`, `"platforms"`, `"task_profiles"`

#### Scenario: Google Workspace conditional
- **WHEN** the Google Workspace integration is enabled in the server build
- **THEN** `GET /api/capabilities` SHALL include `"google_workspace"`

- **WHEN** the Google Workspace integration is disabled
- **THEN** `GET /api/capabilities` SHALL NOT include `"google_workspace"`
