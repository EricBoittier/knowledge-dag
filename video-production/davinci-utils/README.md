# DaVinci Utilities

This area maps the existing DaVinci Resolve, timeline, overlay, and preview tooling.

## Current Code

- `../../video-pipeline/src/run_pipeline.py`: one-command Python orchestration.
- `../../video-pipeline/src/build_timeline_fcpxml.py`: sequential FCPXML generation.
- `../../video-pipeline/src/overlay_manifest.py`: overlay and subtitle schema validation.
- `../../video-pipeline/src/overlay_scheduler.py`: sentence-timed image event scheduling.
- `../../video-pipeline/src/subtitle_builder.py`: `.ass` and `.srt` generation.
- `../../video-pipeline/src/compose_overlay_preview.py`: FFmpeg preview composition.
- `../../video-pipeline/src/prebake_overlay_clips.py`: DaVinci-safe burned-in overlay clips.
- `../../ai-director-app/packages/timeline-davinci/src/export.ts`: TypeScript FCPXML export used by AI Director.

## Common Commands

```bash
cd video-pipeline
python3 src/run_pipeline.py --config ./project_config.json
python3 src/run_pipeline.py --config ./project_config.json --showcase --with-overlays --with-preview
```

## Outputs

- `video-pipeline/output/normalized/manifest.json`
- `video-pipeline/output/overlays/subtitles.srt`
- `video-pipeline/output/overlays/subtitles.ass`
- `video-pipeline/output/overlays/image_events.json`
- `video-pipeline/output/overlays/preview_overlay.mp4`
- `video-pipeline/output/timeline_davinci_resolve.fcpxml`

Design notes live under `docs/`.
