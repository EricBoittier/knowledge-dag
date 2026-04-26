#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ts_srt(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours = total_ms // 3_600_000
    rem = total_ms % 3_600_000
    minutes = rem // 60_000
    rem = rem % 60_000
    secs = rem // 1_000
    millis = rem % 1_000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def wrap_text(text: str, max_chars_per_line: int, max_lines_per_cue: int) -> str:
    words = text.strip().split()
    if not words:
        return ""
    lines: List[str] = []
    line: List[str] = []
    line_len = 0
    for w in words:
        needs = len(w) if not line else len(w) + 1
        if line and line_len + needs > max_chars_per_line and len(lines) + 1 < max_lines_per_cue:
            lines.append(" ".join(line))
            line = [w]
            line_len = len(w)
        else:
            line.append(w)
            line_len += needs
    if line:
        lines.append(" ".join(line))
    return "\n".join(lines[:max_lines_per_cue])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SRT and text transcript from transcript JSON.")
    parser.add_argument("--config", required=True, help="pipeline.config.json path")
    parser.add_argument("--repo-root", required=True, help="repo root path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_json(Path(args.config).resolve())
    transcript_path = Path(cfg["transcription"]["output_transcript_json"]).resolve()
    srt_path = Path(cfg["subtitles"]["output_srt"]).resolve()
    txt_path = Path(cfg["subtitles"]["output_text"]).resolve()

    transcript = load_json(transcript_path)
    segments = transcript.get("segments", [])
    max_chars = int(cfg["subtitles"].get("max_chars_per_line", 42))
    max_lines = int(cfg["subtitles"].get("max_lines_per_cue", 2))

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)

    srt_lines: List[str] = []
    txt_lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        speaker = str(seg.get("speaker", "SPEAKER_00"))
        text = str(seg.get("text", "")).strip()
        line_text = f"[{speaker}] {text}" if text else f"[{speaker}]"
        wrapped = wrap_text(line_text, max_chars, max_lines)
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start + 1))
        srt_lines.extend([str(i), f"{ts_srt(start)} --> {ts_srt(end)}", wrapped, ""])
        txt_lines.append(line_text)

    srt_path.write_text("\n".join(srt_lines).strip() + "\n", encoding="utf-8")
    txt_path.write_text("\n".join(txt_lines).strip() + "\n", encoding="utf-8")

    print(f"Subtitles written: {srt_path}")
    print(f"Transcript text written: {txt_path}")
    if args.dry_run:
        print("[dry-run] Subtitles generated from transcript JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
