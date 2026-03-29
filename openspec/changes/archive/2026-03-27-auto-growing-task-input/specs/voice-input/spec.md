## MODIFIED Requirements

### Requirement: Transcription result inserted into input

When transcription completes successfully, the transcript text SHALL be appended to the existing textarea value (with a space separator if the textarea is not empty). The textarea SHALL receive focus after insertion so the user can review and edit before submitting. After insertion, the textarea height SHALL be recalculated to fit the updated content.

#### Scenario: Transcript appended to empty textarea

- **WHEN** transcription returns "Schedule a meeting with the team for Friday" and the textarea is empty
- **THEN** the textarea value becomes "Schedule a meeting with the team for Friday" and the textarea height adjusts to fit the content

#### Scenario: Transcript appended to existing text

- **WHEN** transcription returns "add details later" and the textarea contains "Review PR"
- **THEN** the textarea value becomes "Review PR add details later" and the textarea height adjusts to fit the content

#### Scenario: Transcription in progress indicator

- **WHEN** audio has been sent for transcription and the response has not yet returned
- **THEN** the microphone button shows a loading spinner and is disabled

#### Scenario: Transcription error

- **WHEN** the transcription request fails (network error or server error)
- **THEN** an error message is displayed below the form: "Voice transcription failed. Please try again or type your task."
