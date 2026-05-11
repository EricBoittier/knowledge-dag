# Video Production

This domain groups the tooling for creating videos from scripts, generated media, overlays, voiceover, and DaVinci Resolve timelines.

The runnable projects still live in their original locations:

- `ai-director-app/` owns the DAG-driven project flow and local desktop shell.
- `video-pipeline/` owns DaVinci-safe normalization, overlays, preview renders, and FCPXML timelines.
- `voice_tts/` provides CSM voiceover synthesis used by the video flows.

## Subdomains

- `davinci-utils/`: DaVinci Resolve import/export, FCPXML, subtitles, overlays, and preview composition.
- `content-generation/`: AI-generated audio, video, image, b-roll, and style-transfer utilities.
- `script-development/`: AI/Human script planning, edit annotations, and DAG expansion.

For cross-project file expectations, see `../shared-contracts/media-and-timeline.md`.
