## 1. Add VAD dependency

- [ ] 1.1 Add `@ricky0123/vad-web` to the component library's `package.json` dependencies. Run `npm install` and verify the package resolves.
- [ ] 1.2 Verify the ONNX model files are accessible (vad-web bundles them or they need to be copied to the public directory — check the library's setup instructions).

## 2. Implement VAD-segmented recording in AudioRecorder

- [ ] 2.1 Add a `MicVAD` instance (from `@ricky0123/vad-web`) that is created lazily on first recording start. Store it as a module-level variable so it persists across recording sessions (model only loaded once).
- [ ] 2.2 Refactor `startRecording()`: after getting the media stream, initialise the VAD listener with `onSpeechEnd` callback. Each `onSpeechEnd` receives the speech audio segment.
- [ ] 2.3 Implement segment dispatch: on each `onSpeechEnd`, assign the segment a sequence number, convert to Blob, and call `api.transcribeAudio(blob)` without awaiting (fire-and-forget with result handling).
- [ ] 2.4 Implement the ordered results array: maintain a `segments: Array<string | null>` reactive ref. When a transcription completes, slot the result at its sequence index. Compute assembled text as `segments.filter(Boolean).join(' ')`.
- [ ] 2.5 Emit progressive `transcription` events: after each segment result is slotted, emit `{ text: assembledText, streaming: true }` to the parent.

## 3. Handle recording stop and finalisation

- [ ] 3.1 Refactor `stopRecording()`: stop the VAD listener, flush any remaining audio as a final segment (if the VAD has buffered audio since the last `onSpeechEnd`).
- [ ] 3.2 Track pending transcriptions with a counter (increment on dispatch, decrement on completion/failure). After stop, when pending count reaches 0, emit final `{ text: assembledText, streaming: false }`.
- [ ] 3.3 Show the transcribing spinner only after stop while pending count > 0. Clear it when all segments complete.
- [ ] 3.4 Reset segment state (sequence counter, segments array, pending count) at the start of each new recording session.

## 4. Error handling

- [ ] 4.1 On individual segment transcription failure, mark that segment as failed (null in the array) and continue. Do not emit an error event.
- [ ] 4.2 After all segments have completed or failed, if ALL segments failed, emit the error event "Voice transcription failed. Please try again or type your task." If at least one succeeded, deliver the partial assembled text without error.

## 5. Update parent integration (TaskForm)

- [ ] 5.1 Update the `onTranscription` handler in TaskForm to accept the new event shape `{ text: string, streaming: boolean }`. When `streaming: true`, replace the voice-contributed portion of the input (track the start position of voice text). When `streaming: false`, finalise the voice text.
- [ ] 5.2 Ensure backward compatibility: if the event is a plain string (old format), treat it as a non-streaming final result.

## 6. Tests

- [ ] 6.1 Unit test: VAD produces segments on speech pauses — mock `@ricky0123/vad-web` to emit `onSpeechEnd` events and verify segments are dispatched to `transcribeAudio`.
- [ ] 6.2 Unit test: out-of-order results are assembled correctly — mock `transcribeAudio` to resolve in different orders and verify the assembled text is sequence-ordered.
- [ ] 6.3 Unit test: progressive `transcription` events are emitted with `streaming: true` during recording and `streaming: false` after stop.
- [ ] 6.4 Unit test: partial failure — mock one segment to reject, verify remaining segments are assembled and no error event is emitted.
- [ ] 6.5 Unit test: total failure — mock all segments to reject, verify error event is emitted.
- [ ] 6.6 Unit test: stop recording flushes remaining audio as a final segment.
- [ ] 6.7 Update existing AudioRecorder tests that expect single-blob recording behaviour.
