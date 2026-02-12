### Requirement: Microphone recording button

The task creation form SHALL display a microphone icon button adjacent to the text input, but only when two conditions are met: (1) the browser supports the `MediaRecorder` API, and (2) the backend reports transcription is enabled via `GET /api/transcribe/status`. If either condition is not met, the microphone button SHALL NOT be rendered.

Clicking the button SHALL request microphone permission (if not already granted) and start audio recording using the `MediaRecorder` API. Clicking the button again SHALL stop recording. While recording, the button SHALL display a visual indicator (red colour with pulsing animation) and show an elapsed time counter.

#### Scenario: Transcription enabled — button shown
- **WHEN** the kanban board loads, MediaRecorder is supported, and `GET /api/transcribe/status` returns `{"enabled": true}`
- **THEN** the microphone button is displayed in the task creation form

#### Scenario: Transcription not configured — button hidden
- **WHEN** the kanban board loads and `GET /api/transcribe/status` returns `{"enabled": false}`
- **THEN** the microphone button is not rendered

#### Scenario: MediaRecorder not supported — button hidden
- **WHEN** the browser does not support the MediaRecorder API
- **THEN** the microphone button is not rendered (regardless of transcription status)

#### Scenario: Start recording
- **WHEN** the user clicks the microphone button and microphone permission is granted
- **THEN** audio recording starts, the button turns red with a pulsing animation, and an elapsed time counter appears

#### Scenario: Stop recording
- **WHEN** the user clicks the microphone button while recording is active
- **THEN** recording stops and the captured audio is sent to `POST /api/transcribe`

#### Scenario: First-time microphone permission
- **WHEN** the user clicks the microphone button for the first time and no microphone permission has been granted
- **THEN** the browser displays its native microphone permission prompt

#### Scenario: Microphone permission denied
- **WHEN** the user denies microphone permission
- **THEN** an error message is displayed: "Microphone access is required for voice input"

### Requirement: Transcription result inserted into input

When transcription completes successfully, the transcript text SHALL be appended to the existing text input value (with a space separator if the input is not empty). The text input SHALL receive focus after insertion so the user can review and edit before submitting.

#### Scenario: Transcript appended to empty input
- **WHEN** transcription returns "Schedule a meeting with the team for Friday" and the text input is empty
- **THEN** the text input value becomes "Schedule a meeting with the team for Friday"

#### Scenario: Transcript appended to existing text
- **WHEN** transcription returns "add details later" and the text input contains "Review PR"
- **THEN** the text input value becomes "Review PR add details later"

#### Scenario: Transcription in progress indicator
- **WHEN** audio has been sent for transcription and the response has not yet returned
- **THEN** the microphone button shows a loading spinner and is disabled

#### Scenario: Transcription error
- **WHEN** the transcription request fails (network error or server error)
- **THEN** an error message is displayed below the form: "Voice transcription failed. Please try again or type your task."

### Requirement: Audio format

The voice input SHALL capture audio using the browser's default `MediaRecorder` codec (typically WebM/Opus on Chrome/Firefox, MP4/AAC on Safari). No client-side audio format conversion SHALL be performed.

#### Scenario: Chrome/Firefox audio format
- **WHEN** recording on Chrome or Firefox
- **THEN** the captured audio is in WebM/Opus format

#### Scenario: Safari audio format
- **WHEN** recording on Safari
- **THEN** the captured audio is in MP4/AAC format (or whatever the browser's default MIME type is)
