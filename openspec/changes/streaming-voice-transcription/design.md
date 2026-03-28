## Context

The AudioRecorder component in `@errand-ai/ui-components` captures audio using the MediaRecorder API, records a single continuous blob, and sends it to `POST /api/transcribe` (Whisper) when the user stops recording. For long dictations (30-120+ seconds), this means no feedback during recording and a potentially long wait for the full transcription at the end.

The backend transcription endpoint accepts any audio file and returns text — it has no awareness of whether the file is a full recording or a short segment. This means we can send multiple shorter audio files without any backend changes.

The `transcribeAudio(blob)` API method in the component library returns `Promise<string>` and can be called concurrently.

## Goals / Non-Goals

**Goals:**
- Show transcribed text appearing progressively in the task input while the user is still speaking
- Use Voice Activity Detection (VAD) to segment audio at natural speech pauses rather than fixed intervals
- Maintain correct text ordering when transcription responses arrive out of sequence
- Acceptable latency: ~3 seconds from speech to text appearing

**Non-Goals:**
- Real-time (<500ms) transcription — that would require WebSocket-based streaming APIs (e.g. OpenAI Realtime API)
- Browser-native Web Speech API integration (different codepath, browser-dependent)
- Backend changes or new API endpoints
- Word-level timestamps or confidence scores
- Editing or correcting individual segments after transcription

## Decisions

### 1. VAD library: `@ricky0123/vad-web` (Silero VAD)

**Decision**: Use `@ricky0123/vad-web` for browser-side voice activity detection.

**Rationale**: Silero VAD is a well-maintained, MIT-licensed library that runs a small ONNX model (~1.5MB) in a Web Worker. It provides `onSpeechStart` and `onSpeechEnd` callbacks with the audio segment data, which maps directly to our need for phrase-level segmentation. The model runs locally with no network dependency.

**Alternatives considered**:
- Fixed-interval chunking (e.g. every 5 seconds) — simpler but cuts mid-word/sentence, causing transcription artifacts
- `hark` (simple energy-based VAD) — less accurate than neural VAD, poor performance in noisy environments
- WebSocket-based streaming to server-side VAD — unnecessary complexity, backend changes required

### 2. Segment dispatch: parallel with sequence-ordered reassembly

**Decision**: Assign each VAD segment a monotonically increasing sequence number at capture time. Send all segments to `POST /api/transcribe` concurrently. Store results in an ordered array indexed by sequence number. Display text as `segments.filter(Boolean).join(' ')`.

**Rationale**: Parallel dispatch minimises end-to-end latency — a later segment doesn't wait for an earlier one to finish transcribing. The sequence number ensures correct ordering regardless of which response arrives first. The display is recomputed whenever any result arrives, so text progressively fills in.

**Data structure**:
```
segments: Array<string | null>  // indexed by sequence number
// e.g. [null, "compare prices", null] → displays "compare prices"
// then ["research flights", "compare prices", null] → displays "research flights compare prices"
```

### 3. Progressive emission via multiple `transcription` events

**Decision**: Emit a `transcription` event each time the assembled text changes (i.e. whenever a segment result arrives). The event payload is the full assembled text from all completed segments so far.

**Rationale**: The parent TaskForm's `onTranscription` callback currently appends text to the input. For streaming, we need to replace the "streaming portion" rather than append each segment independently (which would cause duplication). Two options:

- **Option A**: Emit incremental segment text, let parent append each one → simple but parent can't distinguish "new segment from current recording" vs "new recording session"
- **Option B**: Track a `streamingText` ref inside AudioRecorder, emit the full assembled text, let parent replace the streaming portion → cleaner separation

**Decision**: Option B. AudioRecorder tracks assembled text internally and emits progressive updates. The parent replaces the voice-contributed portion of the input rather than appending. This requires a minor protocol change: the `transcription` event gains a `streaming: boolean` property so the parent knows whether to append (final) or replace (in-progress).

### 4. ONNX model loading and caching

**Decision**: Load the Silero VAD ONNX model lazily on first recording attempt, not on component mount.

**Rationale**: The model is ~1.5MB and requires ONNX Runtime Web. Loading it eagerly would slow down initial page load for all users, including those who never use voice input. Lazy loading means only users who click the microphone button incur the download. The model will be cached by the browser's HTTP cache after first load.

### 5. Recording lifecycle

**Decision**: When the user clicks the microphone button to start recording, initialise the VAD listener on the audio stream. Each `onSpeechEnd` event produces a segment that is immediately dispatched for transcription. When the user clicks stop, flush any remaining audio as a final segment.

The recording timer and red pulsing indicator continue to display throughout the recording session as they do today. The "transcribing" spinner is shown after the user clicks stop, while any remaining segments are still being transcribed — it clears when all pending segments have completed.

## Risks / Trade-offs

- **VAD sensitivity**: If the VAD threshold is too aggressive, it may split segments in the middle of sentences during brief pauses. Mitigation: use the default Silero VAD parameters which are tuned for speech detection; allow configuration of `minSpeechDuration` and `minSilenceDuration` if needed.
- **ONNX model size**: ~1.5MB download on first use. Mitigated by lazy loading and browser caching. Acceptable for a feature that's opt-in (only loaded when user clicks microphone).
- **Very short segments**: A 0.5s segment may not transcribe well with Whisper. Mitigation: Silero VAD has a configurable `minSpeechDuration` (default 250ms) — we can raise this if short segments produce poor results.
- **Concurrent API calls**: A long dictation could produce many concurrent transcription requests. Mitigated by natural speech patterns (humans pause every few seconds, not every 250ms) and the backend's async handling. Typically expect 5-15 segments per minute of speech.
- **Text assembly edge cases**: Whisper may capitalise the start of each segment independently (each segment looks like a new sentence). Acceptable — the text is a task description, not a polished document. Users can edit before submitting.
