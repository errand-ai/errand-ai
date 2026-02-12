## MODIFIED Requirements

### Requirement: Task creation form includes voice input

_(Append to existing task creation form behaviour)_

The task creation form SHALL display a microphone icon button between the text input and the "Add Task" button, but only when voice input is available (browser supports `MediaRecorder` AND `GET /api/transcribe/status` returns `{"enabled": true}`). The form layout SHALL accommodate the microphone button without breaking the existing responsive design. When voice input is not available, the form SHALL render unchanged (text input + "Add Task" button only).

#### Scenario: Form with microphone button (transcription enabled)
- **WHEN** the kanban board loads, the browser supports MediaRecorder, and transcription is enabled
- **THEN** the task creation form displays: text input, microphone button, "Add Task" button

#### Scenario: Form without microphone button (transcription disabled)
- **WHEN** the kanban board loads and transcription is not enabled (no model selected by admin)
- **THEN** the task creation form displays only: text input, "Add Task" button (unchanged)

#### Scenario: Form without microphone button (browser unsupported)
- **WHEN** the kanban board loads in a browser not supporting MediaRecorder
- **THEN** the task creation form displays only: text input, "Add Task" button (unchanged)

#### Scenario: Voice input populates text field
- **WHEN** the user records audio and transcription succeeds
- **THEN** the transcript text appears in the text input field, ready for the user to review and submit with "Add Task"
