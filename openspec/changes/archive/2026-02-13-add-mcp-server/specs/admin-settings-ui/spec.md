## MODIFIED Requirements

### Requirement: Settings page layout

The Settings page SHALL display a heading "Settings" and four sections: "System Prompt", "MCP Server Configuration", "MCP API Key", and "LLM Models". Each section SHALL have a card-style container with a title and form content. The "LLM Models" section SHALL contain both the title-generation model selector and the task processing model selector. The "MCP API Key" section SHALL be positioned after "MCP Server Configuration".

#### Scenario: Settings page renders sections

- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading and four sections: "System Prompt", "MCP Server Configuration", "MCP API Key", and "LLM Models"

## ADDED Requirements

### Requirement: MCP API Key display section

The Settings page SHALL display an "MCP API Key" section showing the API key loaded from `GET /api/settings` (key `mcp_api_key`). The API key SHALL be masked by default (displayed as `••••••••••••••••` or similar) with a "Reveal" toggle button to show the full key. A "Copy" button SHALL copy the full API key to the clipboard regardless of whether it is currently revealed. After copying, the button SHALL briefly show "Copied!" feedback.

#### Scenario: API key displayed masked

- **WHEN** the Settings page loads and an `mcp_api_key` exists
- **THEN** the "MCP API Key" section displays the key as masked text with "Reveal" and "Copy" buttons

#### Scenario: Reveal API key

- **WHEN** the admin clicks the "Reveal" button
- **THEN** the full API key is displayed in plain text and the button changes to "Hide"

#### Scenario: Hide API key

- **WHEN** the admin clicks the "Hide" button while the key is revealed
- **THEN** the key is masked again and the button changes back to "Reveal"

#### Scenario: Copy API key

- **WHEN** the admin clicks the "Copy" button
- **THEN** the full API key is copied to the clipboard and the button briefly shows "Copied!"

#### Scenario: No API key exists

- **WHEN** the Settings page loads and no `mcp_api_key` exists in the settings response
- **THEN** the section displays a message like "No API key generated. Restart the backend to auto-generate one."

### Requirement: Regenerate API key button

The "MCP API Key" section SHALL include a "Regenerate" button. Clicking it SHALL send `POST /api/settings/regenerate-mcp-key`. On success, the section SHALL update to display the new key (masked by default). A confirmation dialog SHALL appear before regenerating to warn that existing MCP clients will need to be reconfigured.

#### Scenario: Regenerate API key

- **WHEN** the admin clicks the "Regenerate" button and confirms the dialog
- **THEN** the frontend sends `POST /api/settings/regenerate-mcp-key`, the new key is displayed (masked), and a success message appears

#### Scenario: Cancel regeneration

- **WHEN** the admin clicks the "Regenerate" button and cancels the confirmation dialog
- **THEN** no API request is made and the current key remains unchanged

#### Scenario: Regeneration error

- **WHEN** the admin confirms regeneration and the API request fails
- **THEN** an error message is displayed and the current key remains unchanged

### Requirement: Example MCP configuration block

The "MCP API Key" section SHALL display a pre-formatted example JSON configuration block that users can copy into their AI coding tool configuration. The example SHALL use the current page origin to construct the MCP server URL (e.g., `https://<current-host>/mcp`) and include the API key as a Bearer token in the Authorization header. The example SHALL follow the format:

```json
{
  "mcpServers": {
    "content-manager": {
      "url": "https://<host>/mcp",
      "headers": {
        "Authorization": "Bearer <api-key>"
      }
    }
  }
}
```

A "Copy" button SHALL copy the entire configuration block to the clipboard.

#### Scenario: Example config with current host

- **WHEN** the Settings page loads at `https://content-manager.example.com/settings`
- **THEN** the example config block shows `"url": "https://content-manager.example.com/mcp"`

#### Scenario: Example config includes API key

- **WHEN** the Settings page loads and the API key is `abc123def456`
- **THEN** the example config block shows `"Authorization": "Bearer abc123def456"`

#### Scenario: Copy example config

- **WHEN** the admin clicks the "Copy" button on the example config block
- **THEN** the entire JSON configuration is copied to the clipboard with "Copied!" feedback

#### Scenario: Config updates after key regeneration

- **WHEN** the admin regenerates the API key
- **THEN** the example configuration block immediately updates to include the new key
