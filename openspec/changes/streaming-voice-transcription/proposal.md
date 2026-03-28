## Why

When dictating long, complex task descriptions, the current voice input records the entire utterance as a single audio blob, sends it for transcription after the user stops, and dumps the full text into the input at once. For multi-sentence descriptions this means a long silence while recording followed by a wall of text appearing — the user gets no feedback while speaking and cannot see what's being captured until the very end.

## What Changes

- Integrate browser-side Voice Activity Detection (VAD) to detect natural speech pauses and segment audio into phrase-level chunks
- Each audio segment is sent to the existing `/api/transcribe` endpoint independently as it completes
- Transcription results appear progressively in the task input as each segment is transcribed (~3s latency per segment)
- Segments are assigned sequence numbers at capture time; results are slotted into an ordered array to maintain correct text ordering regardless of which transcription completes first
- The existing batch recording mode (record-all-then-transcribe) is replaced by the streaming approach — no separate "batch mode" is retained
- The recording timer and visual indicators continue to work as today

## Capabilities

### New Capabilities

- `streaming-voice-transcription`: VAD-based audio segmentation, parallel chunk transcription with ordered reassembly, progressive text insertion during recording

### Modified Capabilities

- `voice-input`: Recording flow changes from single-blob capture to VAD-segmented streaming; the `onTranscription` callback is emitted multiple times during a single recording session instead of once at the end

## Impact

- **Component library** (`@errand-ai/ui-components`): `AudioRecorder.vue` — major rework of recording logic to use VAD segmentation and parallel transcription
- **Component library**: New dependency on `@ricky0123/vad-web` (Silero VAD, ~1.5MB ONNX model)
- **Frontend** (`TaskForm.vue` / consuming app): The `onTranscription` callback is called multiple times per recording session — current append logic already handles this correctly
- **Backend**: No changes — each segment hits the existing `POST /api/transcribe` endpoint as a shorter audio file
- **No API changes**
