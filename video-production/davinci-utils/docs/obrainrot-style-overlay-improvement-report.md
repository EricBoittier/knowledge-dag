# Overlay and Asset Pipeline Improvement Report

This report uses OBrainRot as a reference implementation for fast social-video assembly, especially around timed subtitles and image overlays.

Reference sources:
- [OBrainRot repository](https://github.com/harvestingmoon/OBrainRot)
- [OBrainRot assets directory](https://github.com/harvestingmoon/OBrainRot/tree/master/assets)

## What OBrainRot does well

- Ships ready-to-use media packs under `assets/` (character folders plus voice samples).
- Uses forced alignment to generate word-level timing, then writes `.ass` subtitle events.
- Applies subtitles in FFmpeg and performs image overlays as a timed layer per sentence.
- Keeps a straightforward pipeline order: scrape -> TTS -> timing -> subtitle render -> image overlay.

## Current gap in this repo (relative to that model)

Your `video-pipeline` already normalizes media and builds DaVinci timelines, but it does not yet provide first-class primitives for:

- timed subtitle track generation from transcripts,
- timed image overlays tied to sentence/segment boundaries,
- reusable asset-pack metadata (voices, image sets, style presets),
- one-command preview renders with burned-in subtitle/overlay layers.

## High-impact improvements

1. Add an `overlay_manifest` schema
- Add optional per-entry fields like:
  - `subtitle_segments`: `[{ "text": "...", "start": 1.2, "end": 2.4 }]`
  - `image_overlays`: `[{ "asset": "spongebob/01.png", "start": 1.2, "end": 2.4, "x": 30, "y": 820 }]`
  - `style`: `{ "font": "Inter", "size": 52, "stroke": 3, "safe_margin": 48 }`
- Keep this independent from normalization so editorial and media prep remain decoupled.

2. Add subtitle generation stage before timeline export
- Produce both:
  - `.ass` (for high-quality burn-in preview), and
  - `.srt` (for NLE import and manual adjustment).
- Prefer sentence-level segmentation first; optionally switch to word-level if ASR confidence is high.

3. Add image overlay scheduler
- Implement a deterministic policy:
  - rotate image every sentence by default,
  - optional keyword-to-image mapping table,
  - fallback to round-robin if no keyword hit.
- Add constraints to avoid overlap with subtitles (safe-zone aware placement).

4. Add FFmpeg preview compositor command
- Generate `output/preview_overlay.mp4` from:
  - normalized video,
  - generated subtitle file,
  - image overlay events.
- This gives a quick review render before Resolve import and catches timing issues early.

5. Extend FCPXML export with annotation lanes
- Preserve overlay event timing as markers or connected clips metadata in timeline XML.
- Even if final compositing is in Resolve, keep timing parity between preview and edit timeline.

## Suggested directory structure

```text
video-pipeline/
  input/
    assets/
      obrainrot/               # synced by script
  output/
    overlays/
      subtitles.ass
      subtitles.srt
      image_events.json
      preview_overlay.mp4
  src/
    build_overlay_manifest.py
    build_subtitles.py
    compose_overlay_preview.py
```

## Practical quality improvements

- Normalize overlay images to a consistent max size (for example `512x512`) and alpha-safe PNG.
- Enforce subtitle line length limits (mobile-first readability).
- Add style profiles (`tiktok`, `youtube_shorts`, `default`) instead of hard-coded values.
- Add regression fixtures: same script + same assets should produce stable timings and clip counts.

## Security and maintainability notes

- Pin external asset sources by commit SHA in scripts for reproducible pulls.
- Keep third-party assets in a dedicated path and document license provenance.
- Add CI validation for overlay manifests (schema check + timing monotonicity).

## Next implementation order

1. `build_subtitles.py` (ASS + SRT writer)
2. `build_overlay_manifest.py` (sentence -> image event mapping)
3. `compose_overlay_preview.py` (FFmpeg burn-in renderer)
4. Hook into `src/run_pipeline.py` with an opt-in `--with-overlays` flag
5. Extend timeline export for marker parity
