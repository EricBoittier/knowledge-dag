# AutoSubs Parity Checklist

This checklist tracks feature parity work against AutoSubs.

Reference: [tmoroney/auto-subs](https://github.com/tmoroney/auto-subs)

## Current Status Snapshot

- `dag-video-editor` currently handles planning, discovery, clip selection, normalization, and timeline export.
- `video-pipeline` currently handles normalization, validation, and FCPXML generation.
- No end-to-end local transcription pipeline exists yet in this repo.

## Feature Matrix

### 1) Local AI transcription (no cloud dependency)

- **Target parity:** local speech-to-text for audio/video input, offline-capable.
- **Current status:** missing.
- **Implementation tasks:**
  - Add `src-py/transcribe/` package with model runner abstraction.
  - Implement initial backend using `faster-whisper` (CPU/GPU autodetect).
  - Add chunking and timestamp alignment output (`segments`, `words`).
  - Add CLI command: `run-mvp --from-stage transcribe --to-stage subtitles`.
  - Add model cache directory config and model lifecycle docs.
- **Acceptance criteria:**
  - Given a local media file, command generates transcript with timestamps.
  - Pipeline works without external API keys.

### 2) Speaker diarization + automatic labels/colors

- **Target parity:** identify speakers and apply stable labels.
- **Current status:** missing.
- **Implementation tasks:**
  - Add diarization module (`pyannote.audio` or `whisperx` diarization path).
  - Merge diarization turns with transcript segments.
  - Generate deterministic speaker color map in project output.
  - Persist to `data/speaker-map.json`.
- **Acceptance criteria:**
  - Transcript contains speaker IDs per segment.
  - Re-runs preserve label/color consistency for same input.

### 3) Translation to English

- **Target parity:** optional translation workflow.
- **Current status:** missing.
- **Implementation tasks:**
  - Add translation stage with local-first approach (`NLLB`/Marian or model translation mode).
  - Keep source transcript + translated transcript side-by-side.
  - Add config toggle: `translation.enabled`, `translation.target_language`.
- **Acceptance criteria:**
  - Non-English source can produce English subtitle track.
  - Source-language timestamps remain aligned after translation.

### 4) Export to SRT / text / Resolve

- **Target parity:** output formats usable in standalone and Resolve workflows.
- **Current status:** partial (`SRT` builder exists, Resolve timeline exists).
- **Implementation tasks:**
  - Produce final `subtitles.srt` from transcript+diarization pipeline.
  - Add plain text export (`transcript.txt` and `transcript.md`).
  - Ensure Resolve import flow includes subtitle artifact references.
- **Acceptance criteria:**
  - Generated files exist: `.srt`, `.txt`, `.md`.
  - SRT can be imported as subtitle track in DaVinci Resolve.

### 5) Per-speaker subtitle styling for Resolve

- **Target parity:** speaker-specific color/outline/border styling in Resolve workflow.
- **Current status:** missing.
- **Implementation tasks:**
  - Define `subtitle-style.json` schema with per-speaker style settings.
  - Add Resolve-specific style export (FCPXML annotations or Resolve script hook).
  - Add validation script for style compatibility.
- **Acceptance criteria:**
  - Speaker style config is generated and editable.
  - Resolve workflow can apply distinguishable per-speaker styles.

### 6) "Generate Subtitles & Label Speakers" UX path

- **Target parity:** one-command or one-click flow from input media to labeled subtitles.
- **Current status:** missing.
- **Implementation tasks:**
  - Add single command entrypoint:
    - `npm run subtitles -- --input <path> [--translate en]`
  - Expose progress logs and stage summaries.
  - Add desktop shell action (if using `ai-director-app/apps/desktop` UI).
- **Acceptance criteria:**
  - Single command produces transcript, speaker labels, and subtitle exports.
  - User can run without manually invoking each stage.

## Minimum Technical Plan (Execution Order)

1. Implement transcription stage + data schema.
2. Add diarization and merge logic.
3. Generate SRT/text exports from merged transcript.
4. Add translation and dual-track export.
5. Add Resolve speaker styling output.
6. Add one-command UX wrapper + docs/tests.

## Suggested Test Fixtures

- Short English single-speaker clip.
- Multi-speaker interview clip.
- Non-English clip for translation validation.
- Noisy clip to test fallback behavior.

## Definition of Done

- End-to-end local subtitle generation with speaker labels.
- Optional English translation stage.
- Reliable exports to SRT/text and Resolve workflow compatibility.
- Documented quick start and reproducible integration tests.
