## MODIFIED Requirements

### Requirement: Settings page layout

The Settings page SHALL display a heading "Settings" and five sections: "System Prompt", "MCP Server Configuration", "MCP API Key", "Git SSH Key", and "LLM Models". Each section SHALL have a card-style container with a title and form content. The "LLM Models" section SHALL contain both the title-generation model selector and the task processing model selector. The "MCP API Key" section SHALL be positioned after "MCP Server Configuration". The "Git SSH Key" section SHALL be positioned after "MCP API Key".

#### Scenario: Settings page renders sections

- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading and five sections: "System Prompt", "MCP Server Configuration", "MCP API Key", "Git SSH Key", and "LLM Models"

## ADDED Requirements

### Requirement: Git SSH Key section displays public key

The Settings page SHALL display a "Git SSH Key" section containing a read-only display of the SSH public key loaded from `GET /api/settings` (key `ssh_public_key`). The public key SHALL be displayed in a monospace font code block. A "Copy" button SHALL copy the full public key to the clipboard. After copying, the button SHALL briefly show "Copied!" feedback. Below the public key, the section SHALL display a help text: "Add this key as a deploy key to your Git repositories. Enable write access if you want the agent to push changes."

#### Scenario: Public key displayed

- **WHEN** the Settings page loads and an `ssh_public_key` exists
- **THEN** the "Git SSH Key" section displays the public key in a monospace code block with a "Copy" button

#### Scenario: Copy public key

- **WHEN** the admin clicks the "Copy" button next to the public key
- **THEN** the full public key is copied to the clipboard and the button briefly shows "Copied!"

#### Scenario: No SSH key exists

- **WHEN** the Settings page loads and no `ssh_public_key` exists in the settings response
- **THEN** the section displays a message "No SSH key generated. Restart the backend to auto-generate one."

### Requirement: Regenerate SSH keypair button

The "Git SSH Key" section SHALL include a "Regenerate" button. Clicking it SHALL display a confirmation dialog warning that existing deploy keys configured with the current public key will stop working. On confirmation, the button SHALL send `POST /api/settings/regenerate-ssh-key`. On success, the section SHALL update to display the new public key.

#### Scenario: Regenerate SSH keypair

- **WHEN** the admin clicks the "Regenerate" button and confirms the dialog
- **THEN** the frontend sends `POST /api/settings/regenerate-ssh-key`, the new public key is displayed, and a success message appears

#### Scenario: Cancel regeneration

- **WHEN** the admin clicks the "Regenerate" button and cancels the confirmation dialog
- **THEN** no API request is made and the current key remains unchanged

#### Scenario: Regeneration error

- **WHEN** the admin confirms regeneration and the API request fails
- **THEN** an error message is displayed and the current key remains unchanged

### Requirement: Git SSH hosts configuration

The "Git SSH Key" section SHALL include an editable list of git repository hosts that should use SSH authentication. The list SHALL load its current value from `GET /api/settings` (key `git_ssh_hosts`). If no `git_ssh_hosts` setting exists, the list SHALL default to `["github.com", "bitbucket.org"]`. Each host entry SHALL have a remove button. An "Add Host" input and button SHALL allow adding new hostnames. A "Save" button SHALL send the updated list via `PUT /api/settings` with `{"git_ssh_hosts": [<hosts>]}`.

#### Scenario: Load existing hosts

- **WHEN** the Settings page loads and `git_ssh_hosts` is set to `["github.com", "gitlab.com"]`
- **THEN** the host list displays "github.com" and "gitlab.com" with remove buttons

#### Scenario: Load default hosts

- **WHEN** the Settings page loads and no `git_ssh_hosts` setting exists
- **THEN** the host list displays "github.com" and "bitbucket.org"

#### Scenario: Add a host

- **WHEN** the admin types "gitlab.com" in the add host input and clicks "Add Host"
- **THEN** "gitlab.com" appears in the host list

#### Scenario: Remove a host

- **WHEN** the admin clicks the remove button next to "bitbucket.org"
- **THEN** "bitbucket.org" is removed from the host list

#### Scenario: Save hosts

- **WHEN** the admin modifies the host list and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"git_ssh_hosts": [<updated-hosts>]}` and displays a success indication

#### Scenario: Duplicate host prevented

- **WHEN** the admin tries to add "github.com" but it already exists in the list
- **THEN** the host is not added and a validation message is displayed

#### Scenario: Empty hostname prevented

- **WHEN** the admin clicks "Add Host" with an empty input
- **THEN** no host is added
