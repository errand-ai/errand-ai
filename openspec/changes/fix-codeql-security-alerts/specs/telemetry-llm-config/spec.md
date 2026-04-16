## MODIFIED Requirements

### Requirement: LLM provider category classification
The telemetry module SHALL classify each configured LLM provider's base URL into a category by inspecting the URL's authority (host and port), not by substring-matching the full URL. A URL SHALL be classified as a well-known provider only when its parsed host exactly matches (or, for Ollama, matches a localhost form of) that provider's canonical endpoint host. URLs whose host does not match any well-known endpoint SHALL fall through to the generic categories (`litellm-other`, `openai-compatible-other`, or `other`).

#### Scenario: OpenAI provider
- **WHEN** a provider's base URL has host `api.openai.com` (case-insensitive)
- **THEN** the provider category SHALL be `openai`

#### Scenario: Anthropic provider
- **WHEN** a provider's base URL has host `api.anthropic.com` (case-insensitive)
- **THEN** the provider category SHALL be `anthropic`

#### Scenario: Google Gemini provider
- **WHEN** a provider's base URL has host `generativelanguage.googleapis.com` (case-insensitive)
- **THEN** the provider category SHALL be `gemini`

#### Scenario: xAI provider
- **WHEN** a provider's base URL has host `api.x.ai` (case-insensitive)
- **THEN** the provider category SHALL be `xai`

#### Scenario: Ollama provider
- **WHEN** a provider's base URL has host `localhost` or `127.0.0.1` on port `11434`
- **THEN** the provider category SHALL be `ollama`

#### Scenario: Malicious URL with well-known host in path
- **WHEN** a provider's base URL is `https://evil.example.com/api.openai.com/v1` (well-known name appears in path, not host)
- **THEN** the provider category SHALL NOT be `openai`; it SHALL be classified by its actual host and fall through to the generic categories (`litellm-other`, `openai-compatible-other`, or `other` depending on `provider_type`)

#### Scenario: Malicious URL with well-known host as subdomain suffix
- **WHEN** a provider's base URL is `https://api.openai.com.attacker.example/v1`
- **THEN** the provider category SHALL NOT be `openai` (the exact-host check rejects the impersonation)

#### Scenario: Unknown LiteLLM provider
- **WHEN** a provider's base URL host does not match any well-known endpoint and the provider_type is `litellm`
- **THEN** the provider category SHALL be `litellm-other`

#### Scenario: Unknown OpenAI-compatible provider
- **WHEN** a provider's base URL host does not match any well-known endpoint and the provider_type is `openai_compatible`
- **THEN** the provider category SHALL be `openai-compatible-other`

#### Scenario: Completely unknown provider
- **WHEN** a provider's base URL host does not match any well-known endpoint and the provider_type is neither `litellm` nor `openai_compatible`
- **THEN** the provider category SHALL be `other`

#### Scenario: Malformed URL
- **WHEN** a provider's base URL cannot be parsed (e.g., it is empty, missing a scheme, or otherwise invalid)
- **THEN** the provider category SHALL fall through to the generic categories (`litellm-other`, `openai-compatible-other`, or `other` depending on `provider_type`), with no exception raised to the caller
