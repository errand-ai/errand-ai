## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

Before writing `mcp.json`, the worker SHALL check whether Perplexity platform credentials exist in the database by calling `load_credentials("perplexity", session)`. If credentials exist, the worker SHALL inject a `"perplexity-ask"` entry into the `mcpServers` object of the MCP configuration with the value `{"url": "$PERPLEXITY_URL"}`. This injection SHALL occur before the existing `substitute_env_vars()` call, so that `$PERPLEXITY_URL` is resolved to the actual service URL. If the MCP configuration from the database already contains a `"perplexity-ask"` key, the database value SHALL take precedence (the injected entry SHALL NOT overwrite it). The worker SHALL NOT use the `USE_PERPLEXITY` environment variable for this check.

When Perplexity credentials exist in the database, the worker SHALL also append a Perplexity usage instruction block to the system prompt before writing `system_prompt.txt` into the container. The instruction block SHALL be appended after the admin-configured system prompt content (separated by two newlines) and SHALL instruct the LLM that it has access to the `perplexity-ask` MCP tool for looking up current information online, conducting web research, or reasoning about topics that require context beyond its training data.

#### Scenario: Perplexity injected when platform credentials exist
- **WHEN** the worker processes a task and Perplexity platform credentials exist in the database
- **THEN** the MCP configuration includes a `"perplexity-ask"` entry with the Perplexity MCP service URL, and the system prompt includes Perplexity usage instructions

#### Scenario: Perplexity not injected when no credentials
- **WHEN** the worker processes a task and no Perplexity platform credentials exist in the database
- **THEN** the MCP configuration does not include a `"perplexity-ask"` entry and the system prompt does not include Perplexity instructions

#### Scenario: Database MCP config takes precedence
- **WHEN** the worker processes a task, Perplexity credentials exist, and the admin-configured MCP servers already contain a `"perplexity-ask"` entry
- **THEN** the admin-configured entry is preserved and the worker does not overwrite it

#### Scenario: USE_PERPLEXITY env var no longer used
- **WHEN** the worker processes a task
- **THEN** the worker does not check the `USE_PERPLEXITY` environment variable for Perplexity configuration
