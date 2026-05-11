#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

from overlay_manifest import validate_subtitle_segments, write_json

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def list_images(asset_dir: Path) -> List[Path]:
    return sorted([p for p in asset_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS])


def pick_image_for_text(images: List[Path], text: str, fallback_index: int, keyword_map: Dict[str, str] | None) -> Path:
    if keyword_map:
        lower = text.lower()
        for keyword, image_name in keyword_map.items():
            if keyword.lower() in lower:
                for path in images:
                    if path.name == image_name:
                        return path
    return images[fallback_index % len(images)]


def build_image_events(
    subtitle_segments: List[Dict[str, float | str]],
    asset_dir: Path,
    video_width: int,
    video_height: int,
    safe_margin: int,
    overlay_width: int,
    overlay_height: int,
    anchor: str = "bottom_left",
    keyword_map: Dict[str, str] | None = None,
) -> List[Dict[str, float | str | int]]:
    segments = validate_subtitle_segments(subtitle_segments)
    images = list_images(asset_dir)
    if not images:
        return []
    if anchor == "bottom_left":
        x = safe_margin
        y = max(safe_margin, video_height - overlay_height - safe_margin)
    elif anchor == "bottom_right":
        x = max(safe_margin, video_width - overlay_width - safe_margin)
        y = max(safe_margin, video_height - overlay_height - safe_margin)
    else:
        x = safe_margin
        y = safe_margin

    events: List[Dict[str, float | str | int]] = []
    for idx, seg in enumerate(segments):
        image = pick_image_for_text(images, seg.text, idx, keyword_map)
        events.append(
            {
                "asset": str(image.resolve()),
                "start": seg.start,
                "end": seg.end,
                "x": x,
                "y": y,
                "width": overlay_width,
                "height": overlay_height,
                "anchor": anchor,
                "sentence_index": idx,
                "source_text": seg.text,
            }
        )
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Build sentence-timed image overlay schedule")
    parser.add_argument("--segments-json", required=True, help="Path to subtitle segments JSON")
    parser.add_argument("--asset-dir", required=True, help="Image asset directory")
    parser.add_argument("--output", required=True, help="Path to output image_events.json")
    parser.add_argument("--video-width", type=int, default=1920)
    parser.add_argument("--video-height", type=int, default=1080)
    parser.add_argument("--safe-margin", type=int, default=64)
    parser.add_argument("--overlay-width", type=int, default=512)
    parser.add_argument("--overlay-height", type=int, default=512)
    parser.add_argument("--anchor", default="bottom_left")
    args = parser.parse_args()

    from overlay_manifest import load_json

    payload = load_json(Path(args.segments_json).resolve())
    segments = payload["subtitle_segments"] if "subtitle_segments" in payload else payload
    events = build_image_events(
        subtitle_segments=segments,
        asset_dir=Path(args.asset_dir).resolve(),
        video_width=args.video_width,
        video_height=args.video_height,
        safe_margin=args.safe_margin,
        overlay_width=args.overlay_width,
        overlay_height=args.overlay_height,
        anchor=args.anchor,
        keyword_map=None,
    )
    write_json(Path(args.output).resolve(), {"image_overlays": events})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
