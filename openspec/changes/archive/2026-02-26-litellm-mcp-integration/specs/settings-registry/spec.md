## ADDED Requirements

### Requirement: litellm_mcp_servers setting
The settings registry SHALL include a `litellm_mcp_servers` entry with no environment variable mapping, `sensitive: false`, and a default value of an empty list `[]`. The value SHALL be a JSON array of server alias strings.

#### Scenario: Default value
- **WHEN** no database entry exists for `litellm_mcp_servers` and no env var is mapped
- **THEN** the resolved value is `[]` with `source: "default"`

#### Scenario: Database value
- **WHEN** the database contains `litellm_mcp_servers` = `["argocd", "perplexity"]`
- **THEN** the resolved value is `["argocd", "perplexity"]` with `source: "database"`
