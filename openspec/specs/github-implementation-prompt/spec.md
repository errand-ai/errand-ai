## Requirements

### Requirement: System prompt template for GitHub Projects tasks

The system SHALL provide a default system prompt template stored as a constant that is used when creating tasks from GitHub Projects webhooks. The template SHALL be parameterized with: `issue_number`, `issue_title`, `repo_owner`, `repo_name`, `issue_url`, `issue_labels` (list), and `errand_task_id`. The trigger's `task_prompt` field, if set, SHALL be appended to the template as additional instructions.

#### Scenario: Template renders with all parameters

- **WHEN** a task is created for issue #42 "Fix auth redirect" in repo "acme/api-server" with labels ["bug"]
- **THEN** the system prompt includes the repo clone URL, issue reference, branch prefix ("bug/"), and all phase instructions

#### Scenario: Task prompt appended

- **WHEN** the trigger has `task_prompt: "Pay special attention to backwards compatibility"`
- **THEN** this text is appended to the rendered system prompt under an "Additional Instructions" section

### Requirement: Phase 1 — Discovery and validation instructions

The system prompt SHALL instruct the task runner to: (1) clone the repository from `https://github.com/{repo_owner}/{repo_name}.git` on the main branch, (2) run `openspec list --json` to discover active changes, (3) if zero changes exist, abort with a structured JSON output and post a comment on the issue stating "No openspec changes found in this repository", (4) if exactly one in-progress change exists, use it, (5) if multiple changes exist, read each change's proposal to find one that references the issue number or title — if exactly one match is found, use it, (6) if multiple changes exist and no clear match is found, abort with a structured JSON output and post a comment on the issue asking for clarification on which change to implement, (7) verify the matched change has all required artifacts (proposal, design, specs, tasks) ready for implementation — if artifacts are missing, abort with a comment explaining which artifacts are missing.

#### Scenario: Single change found

- **WHEN** the repo contains exactly one openspec change with status "in-progress"
- **THEN** the task proceeds with that change

#### Scenario: No changes found

- **WHEN** the repo contains no openspec changes
- **THEN** the task aborts with status "aborted", reason "No openspec changes found", and posts a comment on the issue

#### Scenario: Multiple changes, one matches issue

- **WHEN** the repo contains changes "fix-auth-redirect" and "add-dark-mode", and the proposal for "fix-auth-redirect" references issue #42
- **THEN** the task selects "fix-auth-redirect" and proceeds

#### Scenario: Multiple changes, ambiguous match

- **WHEN** the repo contains multiple changes and none clearly reference the issue
- **THEN** the task aborts and posts a comment: "Multiple openspec changes found. Unable to determine which corresponds to this issue. Please add the change name to the issue description or ensure the change proposal references issue #42."

#### Scenario: Change missing artifacts

- **WHEN** the matched change exists but is missing the tasks artifact
- **THEN** the task aborts and posts a comment: "Openspec change 'fix-auth' is missing required artifacts: tasks. Please complete the change artifacts before moving the issue to Ready."

### Requirement: Phase 2 — Implementation instructions

The system prompt SHALL instruct the task runner to: (1) determine the branch prefix from the issue labels — `bug/` if "bug" label is present, `feature/` if "enhancement" label is present, `patch/` otherwise, (2) create a feature branch named `{prefix}{change-name}` from the main branch, (3) execute the openspec apply workflow to implement all tasks in the change, marking each task as complete in tasks.md as it is done.

#### Scenario: Bug label produces bug/ prefix

- **WHEN** the issue has label "bug" and the change name is "fix-auth-redirect"
- **THEN** the branch is created as `bug/fix-auth-redirect`

#### Scenario: Enhancement label produces feature/ prefix

- **WHEN** the issue has label "enhancement" and the change name is "add-dark-mode"
- **THEN** the branch is created as `feature/add-dark-mode`

#### Scenario: No matching label produces patch/ prefix

- **WHEN** the issue has neither "bug" nor "enhancement" labels
- **THEN** the branch prefix defaults to `patch/`

### Requirement: Phase 3 — Verification and testing instructions

The system prompt SHALL instruct the task runner to: (1) run ALL tests in the repository and ensure they pass, (2) if any tests fail, fix the failures and re-run all tests until they pass, (3) execute the openspec verify workflow to confirm the implementation matches the change artifacts, (4) if verification identifies issues, fix them, (5) after any fixes from verification, run ALL tests again to ensure nothing was broken, (6) repeat the test-fix cycle until all tests pass. The prompt SHALL explicitly state that NO code may be committed or pushed until all tests are passing.

#### Scenario: Tests pass on first run

- **WHEN** all tests pass after implementation
- **THEN** the task proceeds to Phase 4

#### Scenario: Tests fail and are fixed

- **WHEN** tests fail after implementation
- **THEN** the task fixes the failures, re-runs all tests, and only proceeds to Phase 4 when all tests pass

#### Scenario: Verification introduces fixes that break tests

- **WHEN** openspec verify identifies issues, fixes are applied, and those fixes break a test
- **THEN** the task fixes the newly broken test and re-runs all tests before proceeding

### Requirement: Phase 4 — Delivery instructions

The system prompt SHALL instruct the task runner to: (1) commit all changes with a descriptive commit message, (2) push the branch to origin, (3) create a pull request using `gh pr create` with a title derived from the change, a body containing a summary of changes and `Relates to {issue_url}`, (4) post a summary comment on the GitHub issue including the PR URL and a description of work done, (5) output a structured JSON block as the final message.

#### Scenario: Successful delivery

- **WHEN** all tests pass and verification succeeds
- **THEN** the task creates a PR, comments on the issue, and outputs structured JSON with status "completed"

#### Scenario: PR body contains issue reference

- **WHEN** a PR is created for issue #42 at https://github.com/acme/api/issues/42
- **THEN** the PR body includes `Relates to https://github.com/acme/api/issues/42`

### Requirement: Structured JSON output format

The system prompt SHALL instruct the task runner to output a fenced JSON block (```json ... ```) as the final message. For successful completion, the JSON SHALL contain: `status` ("completed"), `change_name` (string), `branch` (string), `pr_number` (integer), `pr_url` (string), `issue_number` (integer), `summary` (string describing work done). For abort cases, the JSON SHALL contain: `status` ("aborted"), `reason` (string explaining why), `issue_number` (integer). The system prompt SHALL explicitly state that this output format is machine-parsed by errand and must not be omitted.

#### Scenario: Completed output format

- **WHEN** the task completes successfully with PR #47
- **THEN** the final output is a JSON block: `{"status": "completed", "change_name": "fix-auth-redirect", "branch": "bug/fix-auth-redirect", "pr_number": 47, "pr_url": "https://github.com/acme/api/pull/47", "issue_number": 42, "summary": "..."}`

#### Scenario: Aborted output format

- **WHEN** the task aborts due to missing openspec changes
- **THEN** the final output is a JSON block: `{"status": "aborted", "reason": "No openspec changes found in this repository", "issue_number": 42}`
