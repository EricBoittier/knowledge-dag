#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from overlay_manifest import load_json


def _escape_filter_path(path: Path) -> str:
    escaped = str(path.resolve())
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    return escaped


def build_filter_complex(image_events: List[Dict[str, Any]], ass_path: Path) -> str:
    subtitle_filter = f"subtitles='{_escape_filter_path(ass_path)}'"
    if not image_events:
        return f"[0:v]{subtitle_filter}[vout]"
    parts: List[str] = []
    for idx, event in enumerate(image_events, start=1):
        parts.append(f"[{idx}:v]scale={event['width']}:{event['height']}[ov{idx}]")
    current = "0:v"
    for idx, event in enumerate(image_events, start=1):
        target = f"vtmp{idx}" if idx < len(image_events) else "vout"
        parts.append(
            f"[{current}][ov{idx}]overlay={event['x']}:{event['y']}:enable='between(t,{event['start']:.3f},{event['end']:.3f})'[{target}]"
        )
        current = target
    parts.append(f"[{current}]{subtitle_filter}[vout]")
    return ";".join(parts)


def compose_preview(video_path: Path, ass_path: Path, image_events_path: Path, output_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but not found in PATH")
    overlay_payload = load_json(image_events_path)
    events = overlay_payload.get("image_overlays", [])
    filter_complex = build_filter_complex(events, ass_path=ass_path)
    cmd: List[str] = ["ffmpeg", "-y", "-i", str(video_path.resolve())]
    for event in events:
        cmd.extend(["-i", str(Path(event["asset"]).resolve())])
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]" if events else "0:v",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path.resolve()),
        ]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg preview compose failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose preview video with subtitles and image overlays")
    parser.add_argument("--video", required=True, help="Input normalized video path")
    parser.add_argument("--ass", required=True, help="ASS subtitle path")
    parser.add_argument("--image-events", required=True, help="image_events.json path")
    parser.add_argument("--output", required=True, help="Output preview video path")
    args = parser.parse_args()
    compose_preview(
        video_path=Path(args.video).resolve(),
        ass_path=Path(args.ass).resolve(),
        image_events_path=Path(args.image_events).resolve(),
        output_path=Path(args.output).resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
