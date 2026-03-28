## MODIFIED Requirements

### Requirement: Microphone recording button

The task creation form SHALL display a microphone icon button adjacent to the text input, but only when two conditions are met: (1) the browser supports the `MediaRecorder` API, and (2) the backend reports transcription is enabled via `GET /api/transcribe/status`. If either condition is not met, the microphone button SHALL NOT be rendered.

Clicking the button SHALL request microphone permission (if not already granted) and start audio recording using the `MediaRecorder` API with Voice Activity Detection (VAD) enabled. The VAD SHALL segment the audio stream at natural speech pauses and dispatch each segment for transcription independently. Clicking the button again SHALL stop recording and flush any remaining audio as a final segment.

While recording, the button SHALL display a visual indicator (red colour with pulsing animation) and show an elapsed time counter. After recording stops, while segment transcriptions are still pending, the button SHALL show a loading spinner and be disabled.

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
- **THEN** audio recording starts with VAD enabled, the button turns red with a pulsing animation, and an elapsed time counter appears

#### Scenario: Stop recording
- **WHEN** the user clicks the microphone button while recording is active
- **THEN** recording stops, any remaining audio is flushed as a final segment, and pending transcriptions complete before the session ends

#### Scenario: First-time microphone permission
- **WHEN** the user clicks the microphone button for the first time and no microphone permission has been granted
- **THEN** the browser displays its native microphone permission prompt

#### Scenario: Microphone permission denied
- **WHEN** the user denies microphone permission
- **THEN** an error message is displayed: "Microphone access is required for voice input"

### Requirement: Transcription result inserted into input

While recording is active, the AudioRecorder SHALL emit progressive `transcription` events with `streaming: true` as each segment is transcribed. The parent component SHALL replace the voice-contributed portion of the input text with the latest assembled text from the streaming session. When the recording session completes (final event with `streaming: false`), the parent component SHALL finalise the voice-contributed text.

After each update, the text input SHALL receive focus so the user can review and edit before submitting. If the input uses an auto-growing textarea, its height SHALL be recalculated after each progressive update.

#### Scenario: Progressive transcript updates during recording
- **WHEN** the user is recording and segment 0 completes with "Schedule a meeting"
- **THEN** the text input shows "Schedule a meeting" (or appended to existing text if present)

#### Scenario: Progressive transcript grows as segments complete
- **WHEN** segment 0 has completed with "Schedule a meeting" and segment 1 completes with "with the team for Friday"
- **THEN** the text input shows "Schedule a meeting with the team for Friday"

#### Scenario: Transcript appended to existing text
- **WHEN** the text input already contains "Review PR" and a streaming session produces "add details later"
- **THEN** the text input value becomes "Review PR add details later"

#### Scenario: Transcription in progress indicator
- **WHEN** the user has stopped recording and segment transcriptions are still pending
- **THEN** the microphone button shows a loading spinner and is disabled

#### Scenario: Transcription error
- **WHEN** all segment transcription requests fail (network error or server error)
- **THEN** an error message is displayed below the form: "Voice transcription failed. Please try again or type your task."

### Requirement: Audio format

The voice input SHALL capture audio using the browser's default `MediaRecorder` codec (typically WebM/Opus on Chrome/Firefox, MP4/AAC on Safari). No client-side audio format conversion SHALL be performed. Each VAD-segmented audio chunk SHALL use the same codec as the original recording stream.

#### Scenario: Chrome/Firefox audio format
- **WHEN** recording on Chrome or Firefox
- **THEN** each segment's captured audio is in WebM/Opus format

#### Scenario: Safari audio format
- **WHEN** recording on Safari
- **THEN** each segment's captured audio is in MP4/AAC format (or whatever the browser's default MIME type is)
