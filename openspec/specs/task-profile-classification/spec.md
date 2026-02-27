## Purpose

LLM classifier extension that selects a task profile based on match rules during task creation.

## Requirements

### Requirement: LLM classifier selects task profile
The `generate_title` function SHALL include available task profiles in the LLM classifier system prompt. Each profile's `name` and `match_rules` SHALL be listed as options. The LLM SHALL return a `profile` field in its JSON response with the selected profile name. If no profiles exist or the LLM omits/returns an unknown profile name, the result SHALL default to `null` (default profile).

#### Scenario: Profile selected by LLM
- **WHEN** a task is created with description "Check my inbox for unread emails" and an "email-triage" profile exists with match_rules "Tasks about email, inbox, mail sorting"
- **THEN** the LLM returns `{"title": "Check Inbox Emails", "category": "immediate", "profile": "email-triage"}`

#### Scenario: LLM returns unknown profile
- **WHEN** the LLM returns `{"title": "...", "category": "immediate", "profile": "nonexistent"}`
- **THEN** the profile is set to null (default profile)

#### Scenario: LLM omits profile field
- **WHEN** the LLM returns `{"title": "...", "category": "immediate"}` without a `profile` field
- **THEN** the profile is set to null (default profile)

#### Scenario: No profiles defined
- **WHEN** no task profiles exist in the database
- **THEN** the classifier prompt does not include a profile selection section and the result profile is null

#### Scenario: LLM failure falls back gracefully
- **WHEN** the LLM call fails or times out
- **THEN** the fallback result has profile set to null (same as existing behavior with "Needs Info" tag)

### Requirement: Profile match rules in classifier prompt
The classifier system prompt SHALL include a section listing available profiles when profiles exist. The format SHALL be: profile name followed by its match_rules text. The prompt SHALL instruct the LLM to select "default" or omit the profile field when no custom profile is a clear match.

#### Scenario: Classifier prompt with profiles
- **WHEN** two profiles exist: "email-triage" (rules: "Tasks about email") and "coding" (rules: "Tasks involving code, PRs")
- **THEN** the classifier system prompt includes both profiles with their match rules and instructs the LLM to pick the best match

#### Scenario: Classifier prompt without profiles
- **WHEN** no custom profiles exist
- **THEN** the classifier system prompt does not include a profile selection section (backward compatible with current prompt)

### Requirement: LLMResult includes profile
The `LLMResult` dataclass SHALL include a `profile` field (string, nullable, default None) containing the LLM-selected profile name. The `_parse_llm_response` function SHALL extract the `profile` field from the LLM's JSON response.

#### Scenario: Parse response with profile
- **WHEN** the LLM response JSON contains `"profile": "email-triage"`
- **THEN** the parsed `LLMResult` has `profile="email-triage"`

#### Scenario: Parse response without profile
- **WHEN** the LLM response JSON does not contain a `profile` field
- **THEN** the parsed `LLMResult` has `profile=None`

### Requirement: Task creation resolves profile_id from LLM result
After the LLM returns a profile name, the task creation logic SHALL look up the `TaskProfile` by name. If found, `profile_id` SHALL be set to the profile's UUID. If not found or null, `profile_id` SHALL be null.

#### Scenario: Profile name resolved to ID
- **WHEN** the LLM returns `profile: "email-triage"` and a profile with that name exists
- **THEN** the created task has `profile_id` set to the email-triage profile's UUID

#### Scenario: Profile name not found
- **WHEN** the LLM returns `profile: "nonexistent"` and no profile with that name exists
- **THEN** the created task has `profile_id = null`

#### Scenario: Short input skips classification
- **WHEN** a task is created with 5 words or fewer (skipping LLM)
- **THEN** the task has `profile_id = null`
