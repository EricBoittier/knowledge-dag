# Repository Map

This repository contains the pieces for a wiki-to-video workflow: develop an idea or script, generate or collect media, synthesize a voiceover, place text and image overlays, and export a DaVinci Resolve timeline.

The current implementation is intentionally split across several runnable projects. The domain folders added in this pass are navigation and documentation layers; they point to the working code without changing package-relative paths.

## Domain Groups

```text
video-production/
  davinci-utils/        DaVinci Resolve, FCPXML, overlays, subtitles, previews
  content-generation/   AI media generation, voiceover generation, pipeline orchestration
  script-development/   AI/Human script planning, DAG expansion, edit annotations
training/
  unsloth/              Unsloth ASR/TTS fine-tuning, datasets, LoRA guidance
guis/
  knowledge-web/        Original knowledge DAG web application
  ai-director/          Local AI Director browser shell
  dataset-tools/        Voice dataset capture and SRT dataset UIs
legacy/
  dag-video-editor.md   Deprecated video editor surface
shared-contracts/
  media-and-timeline.md Cross-project media, overlay, and timeline contracts
```

## Wiki-To-Video Path

1. Start from a concept, wiki topic, or knowledge graph node.
2. Develop a script and edit annotations with the AI Director planner.
3. Discover, select, normalize, or generate video and image assets.
4. Build subtitles, text overlays, image overlays, and preview renders.
5. Generate narration or dialogue with the voice pipeline.
6. Export DaVinci-friendly media plus `timeline_davinci_resolve.fcpxml`.
7. Import media and timeline into DaVinci Resolve for final editing and render.

## Current Runnable Surfaces

- `ai-director-app/` is the canonical DAG-driven video app and desktop shell.
- `video-pipeline/` is the editor-first Python pipeline for DaVinci-safe media, overlays, previews, and FCPXML.
- `voice_tts/` contains Sesame CSM-1B TTS training, synthesis, and dataset preparation.
- `voice_ft/` contains Whisper fine-tuning and a static recording UI for speech datasets.
- The repository root is still the original knowledge DAG web app.
- `dag-video-editor/` is deprecated and kept only as a legacy compatibility surface.

## Start Here By Goal

- Create or run the end-to-end video DAG: `ai-director-app/README.md`
- Normalize clips and build DaVinci timelines: `video-pipeline/README.md`
- Train or synthesize a voice in your style: `voice_tts/README.md`
- Fine-tune Whisper or record ASR datasets: `voice_ft/README.md`
- Run the original knowledge graph web app: `README.md`
- Understand cross-project file contracts: `shared-contracts/media-and-timeline.md`
