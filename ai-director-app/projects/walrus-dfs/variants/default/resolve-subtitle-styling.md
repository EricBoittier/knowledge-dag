# Resolve Subtitle Styling Guide

1. Import `timeline_davinci_resolve.fcpxml` — captions may already be embedded (lane -2) with font/color from config.
2. Alternatively import `subtitles.srt` onto a subtitle track.
3. Open `subtitle-style.json` for per-speaker colors (see `cue_speaker_map`).
4. `subtitle-cues.json` mirrors the same timing as the SRT for tooling.

## Speaker Style Map
- SPEAKER_00: text=#FFFFFF, outline=#101418, shadow=#000000A0