## ADDED Requirements

### Requirement: Menu bar presence
The application SHALL run as a macOS menu bar app using SwiftUI `MenuBarExtra`. The app SHALL display a status icon in the system menu bar. The icon SHALL indicate overall status: idle (no services running), starting, running (all healthy), or degraded (some services unhealthy).

#### Scenario: App appears in menu bar
- **WHEN** the application is launched
- **THEN** an icon appears in the macOS menu bar

#### Scenario: Icon reflects running status
- **WHEN** all managed services are healthy
- **THEN** the menu bar icon shows a "running" state

#### Scenario: Icon reflects degraded status
- **WHEN** one or more services are unhealthy but others are running
- **THEN** the menu bar icon shows a "degraded" state

### Requirement: Service status popover
Clicking the menu bar icon SHALL display a popover showing each managed service with its name, status (stopped/starting/running/error), and port number. The popover SHALL include "Start All", "Stop All", and "Open in Browser" buttons. A settings gear icon SHALL open a settings window.

#### Scenario: Popover shows service list
- **WHEN** the user clicks the menu bar icon
- **THEN** a popover displays all services (PostgreSQL, Valkey, Backend, Worker, and optionally LiteLLM) with their current status

#### Scenario: Open in browser
- **WHEN** the user clicks "Open in Browser" and the backend is running
- **THEN** the default browser opens to `http://localhost:8000`

#### Scenario: Start all services
- **WHEN** the user clicks "Start All"
- **THEN** all services start in dependency order (PostgreSQL first, then Valkey, then Backend, then Worker)

#### Scenario: Stop all services
- **WHEN** the user clicks "Stop All"
- **THEN** all services are stopped in reverse dependency order

### Requirement: Settings window
The app SHALL provide a settings window for configuring: LLM API keys (`OPENAI_BASE_URL`, `OPENAI_API_KEY`), LiteLLM toggle (on/off), OIDC settings (discovery URL, client ID, client secret), and service ports. Settings SHALL be persisted to `~/Library/Application Support/ContentManager/config.json`.

#### Scenario: Settings persisted
- **WHEN** the user changes the `OPENAI_API_KEY` setting and closes the settings window
- **THEN** the value is saved to `config.json` and used on next service start

#### Scenario: LiteLLM toggle
- **WHEN** the user enables LiteLLM in settings
- **THEN** the LiteLLM service appears in the service list and starts with the next "Start All"

### Requirement: Log viewer
The app SHALL provide a log viewer window accessible from the popover. The log viewer SHALL display real-time logs from all running containers, filterable by service. Logs SHALL be streamed from each container's stdout/stderr.

#### Scenario: View backend logs
- **WHEN** the user opens the log viewer and selects "Backend"
- **THEN** the log viewer shows real-time log output from the backend container

### Requirement: Launch at login
The app SHALL offer an option in settings to launch automatically at macOS login using `SMAppService` (the modern macOS login item API).

#### Scenario: Auto-launch enabled
- **WHEN** the user enables "Launch at Login" in settings
- **THEN** the app starts automatically when the user logs in to macOS

### Requirement: First-run setup
On first launch (no `config.json` exists), the app SHALL show a setup assistant that guides the user through: entering LLM API credentials, optionally enabling LiteLLM, and pulling required container images. The setup SHALL show download progress for each image.

#### Scenario: First launch
- **WHEN** the app is launched for the first time
- **THEN** a setup assistant window appears before the menu bar popover is usable

#### Scenario: Image pull progress
- **WHEN** the setup assistant pulls container images
- **THEN** a progress indicator shows the download status for each image
