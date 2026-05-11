# Media And Timeline Contracts

This document records the file contracts that let the current wiki-to-video pieces work together across `ai-director-app`, `video-pipeline`, `voice_tts`, and DaVinci Resolve.

It is documentation only. The first restructure pass does not change these paths.

## Script And Edit Artifacts

AI Director is the canonical owner of script planning and edit annotations.

Typical project files:

- `ai-director-app/projects/<project>/dag.project.json`: source concept, DAG, or topic plan.
- `ai-director-app/projects/<project>/shot-plan.json`: planned shots and source needs.
- `ai-director-app/projects/<project>/script.md`: human-readable narration or script.
- `ai-director-app/projects/<project>/edit-annotations.json`: timing and editorial guidance for clips, captions, overlays, and style.
- `ai-director-app/projects/<project>/candidates.json`: discovered candidate media.
- `ai-director-app/projects/<project>/selected-clips.json`: selected media for the edit.

`video-pipeline` can consume AI Director project metadata with `--gemini-project-dir`.

## Media Manifests

Normalized media is described by JSON manifests.

Common files:

- `ai-director-app/projects/<project>/media-manifest.json`
- `video-pipeline/output/normalized/manifest.json`
- `video-pipeline/output/normalized/manifest.showcase.json`

Manifests should preserve enough information to map source clips to normalized or processed media paths, durations, trim windows, and optional b-roll analysis.

## Subtitle Contracts

The pipeline produces both editable and preview-friendly subtitle formats.

- `.srt` is for DaVinci Resolve import and manual adjustment.
- `.ass` is for FFmpeg preview or burned-in subtitle styling.

Common files:

- `ai-director-app/projects/<project>/subtitles.srt`
- `video-pipeline/output/overlays/subtitles.srt`
- `video-pipeline/output/overlays/subtitles.ass`

Subtitle timings should match the same timeline basis used by overlay events and FCPXML export.

## Overlay Contracts

Overlay data describes timed text and image events independently from normalized media.

Common files:

- `video-pipeline/output/overlays/overlay_manifest.json`
- `video-pipeline/output/overlays/image_events.json`
- `video-pipeline/output/overlays/dialogue_plan.json`
- `video-pipeline/output/overlays/preview_overlay.mp4`

Overlay events should include start and end times, asset references, placement data, and style information when relevant. Placement should respect safe zones for vertical and horizontal exports.

## Voiceover Contracts

Voiceover generation is currently split between AI Director orchestration and the CSM training/synthesis code.

Current owners:

- `ai-director-app/packages/pipeline/src-py/generate_voiceover.py`: pipeline bridge for voiceover generation.
- `voice_tts/scripts/synthesize_sesame_csm.py`: single-utterance CSM synthesis.
- `voice_tts/scripts/synthesize_dialogue_csm.py`: multi-turn dialogue synthesis.

Current model artifacts are referenced in place, for example `voice_tts/sesame_csm_lora*` or root-level `sesame_csm_lora`. Do not move those artifacts until configs and docs are updated together.

Expected generated audio examples:

- `video-pipeline/output/overlays/dialogue_mix.wav`
- AI Director project voiceover files under the relevant project output directory.

Audio intended for DaVinci import should use editor-friendly WAV settings when possible, typically 48 kHz PCM for final timeline assets.

## DaVinci Timeline Contracts

DaVinci Resolve import currently depends on FCPXML plus pre-imported media.

Common files:

- `ai-director-app/projects/<project>/output/timeline_davinci_resolve.fcpxml`
- `video-pipeline/output/timeline_davinci_resolve.fcpxml`
- `video-pipeline/output/timeline_davinci_resolve.horizontal.fcpxml`
- `video-pipeline/output/timeline_davinci_resolve.vertical.fcpxml`
- `ai-director-app/projects/<project>/output/import-report.md`
- `ai-director-app/projects/<project>/output/crop-validation.json`

Expected DaVinci flow:

1. Import normalized or processed media first.
2. Import `timeline_davinci_resolve.fcpxml`.
3. Import `subtitles.srt` if editable subtitles are wanted.
4. Use `import-report.md` and validation output to check asset mapping and crop assumptions.

## Generated Output Policy

Generated media, rendered previews, normalized clips, checkpoints, and downloads can be large. Do not reorganize them casually.

Recommended later policy:

- keep source code and docs in the domain folders,
- keep large model artifacts in a dedicated ignored or LFS-backed artifact tree,
- keep generated video outputs under project-specific `output/` directories,
- document every config path that points across project boundaries before moving it.
