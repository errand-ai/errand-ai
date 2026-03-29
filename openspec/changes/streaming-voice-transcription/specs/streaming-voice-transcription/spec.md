## ADDED Requirements

### Requirement: Voice Activity Detection segmentation

The AudioRecorder SHALL use the `@ricky0123/vad-web` library (Silero VAD) to detect speech boundaries in the audio stream. When the user starts recording, the VAD listener SHALL be initialised on the microphone audio stream. Each time the VAD detects the end of a speech segment (a pause in speech), the captured audio segment SHALL be dispatched for transcription immediately.

The VAD ONNX model SHALL be loaded lazily on the first recording attempt, not on component mount or page load. Subsequent recordings SHALL reuse the already-loaded model.

#### Scenario: VAD segments speech at natural pauses

- **WHEN** the user is recording and speaks "Research flights from London to Paris" then pauses briefly then says "Compare prices across airlines"
- **THEN** the VAD produces two audio segments: one for each phrase separated by the speech pause

#### Scenario: VAD model loaded lazily

- **WHEN** the page loads and the user has not clicked the microphone button
- **THEN** the VAD ONNX model is not downloaded or loaded

#### Scenario: VAD model loaded on first recording

- **WHEN** the user clicks the microphone button for the first time
- **THEN** the VAD ONNX model is loaded before recording begins

#### Scenario: Continuous speech without pauses

- **WHEN** the user speaks continuously for 30 seconds without any pause
- **THEN** the VAD treats the entire utterance as a single segment that is dispatched when the user pauses or stops recording

### Requirement: Parallel chunk transcription with ordered reassembly

Each audio segment produced by the VAD SHALL be assigned a monotonically increasing sequence number at capture time (starting from 0 for each recording session). Segments SHALL be sent to the existing `POST /api/transcribe` endpoint concurrently — a new segment SHALL NOT wait for previous segments to finish transcribing before being sent.

Transcription results SHALL be stored in an ordered array indexed by sequence number. The displayed text SHALL be computed as the concatenation of all non-null entries in the array, joined by spaces, preserving the original speech order regardless of which transcription responses arrive first.

#### Scenario: Results arrive in order

- **WHEN** segment 0 completes with "Research flights" then segment 1 completes with "Compare prices"
- **THEN** the assembled text is "Research flights Compare prices"

#### Scenario: Results arrive out of order

- **WHEN** segment 1 completes with "Compare prices" before segment 0 completes with "Research flights"
- **THEN** after segment 1 arrives, the assembled text is "Compare prices"
- **AND** after segment 0 arrives, the assembled text is "Research flights Compare prices"

#### Scenario: Three segments with middle arriving last

- **WHEN** segment 0 returns "Book the cheapest option", segment 2 returns "that arrives before 2pm", and then segment 1 returns "from London to Paris"
- **THEN** the final assembled text is "Book the cheapest option from London to Paris that arrives before 2pm"

### Requirement: Progressive text display during recording

While recording is active and VAD segments are being transcribed, the assembled text from completed segments SHALL be progressively emitted to the parent component. Each time a segment transcription completes, the AudioRecorder SHALL emit a `transcription` event with the full assembled text from all completed segments so far, along with a `streaming: true` flag.

When the user stops recording and all pending transcriptions have completed, the AudioRecorder SHALL emit a final `transcription` event with `streaming: false` to indicate the recording session is complete.

#### Scenario: First segment result appears during recording

- **WHEN** the user is still recording and the first segment transcription completes with "Research flights from London"
- **THEN** a `transcription` event is emitted with text "Research flights from London" and `streaming: true`

#### Scenario: Second segment result appears during recording

- **WHEN** segment 0 has completed with "Research flights" and segment 1 completes with "Compare prices"
- **THEN** a `transcription` event is emitted with text "Research flights Compare prices" and `streaming: true`

#### Scenario: Final event after recording stops

- **WHEN** the user stops recording and all pending segment transcriptions complete
- **THEN** a `transcription` event is emitted with the full assembled text and `streaming: false`

### Requirement: Recording stop flushes remaining audio

When the user clicks the microphone button to stop recording, any audio captured since the last VAD speech-end event SHALL be flushed as a final segment and sent for transcription. The recording session SHALL not be considered complete until all pending segment transcriptions (including this final flush segment) have finished.

#### Scenario: User stops mid-sentence

- **WHEN** the user is speaking "Book the cheapest" and clicks stop before pausing
- **THEN** the audio captured so far is sent as a final segment for transcription

#### Scenario: User stops during silence

- **WHEN** the user has finished speaking and pauses, then clicks stop with no new speech
- **THEN** no additional segment is dispatched (the last speech was already sent by the VAD)

### Requirement: Transcription progress indicator during streaming

While recording is active, the microphone button SHALL continue to display the red pulsing indicator and elapsed timer (unchanged from current behaviour). After the user clicks stop, while any segment transcriptions are still pending, the microphone button SHALL display a loading spinner and be disabled. The spinner SHALL clear when all pending segments have completed.

#### Scenario: Spinner shown after stop with pending segments

- **WHEN** the user clicks stop and 2 of 5 segments are still being transcribed
- **THEN** the microphone button shows a loading spinner until all 5 segments have completed

#### Scenario: No spinner when all segments already complete

- **WHEN** the user clicks stop and all segments have already been transcribed (they completed during recording)
- **THEN** no spinner is shown; the final transcription event is emitted immediately

### Requirement: Segment transcription error handling

If a segment transcription fails (network error or server error), that segment SHALL be recorded as failed. The remaining segments SHALL continue to be transcribed. The assembled text SHALL include all successfully transcribed segments in order, with failed segments omitted. An error event SHALL be emitted indicating partial transcription failure only if ALL segments fail. If at least one segment succeeds, no error is emitted — the partial text is delivered.

#### Scenario: One segment fails, others succeed

- **WHEN** segment 1 of 3 fails but segments 0 and 2 succeed with "Research flights" and "Book the cheapest"
- **THEN** the assembled text is "Research flights Book the cheapest" (segment 1 omitted) and no error event is emitted

#### Scenario: All segments fail

- **WHEN** all segment transcriptions fail due to a network outage
- **THEN** an error event is emitted with "Voice transcription failed. Please try again or type your task."

#### Scenario: Network error on single segment

- **WHEN** a segment transcription request fails with a network error
- **THEN** that segment is marked as failed, other segments continue processing normally
