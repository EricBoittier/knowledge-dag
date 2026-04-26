#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _format_default_text(entry: Dict[str, Any], idx: int) -> str:
    concept = str(entry.get("concept", "")).strip()
    source_title = str(entry.get("source_title", "")).strip()
    if concept and source_title:
        return f"{concept}: {source_title}"
    if concept:
        return concept
    if source_title:
        return source_title
    return f"Segment {idx}"


def build_dry_run_transcript(manifest_entries: List[Dict[str, Any]], language: str, model: str) -> Dict[str, Any]:
    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    for idx, entry in enumerate(manifest_entries, start=1):
        timeline = entry.get("timeline", {}) if isinstance(entry.get("timeline"), dict) else {}
        timeline_in = float(timeline.get("in_seconds", 0) or 0)
        timeline_out = float(timeline.get("out_seconds", 0) or 0)
        timeline_duration = timeline_out - timeline_in if timeline_out > timeline_in else 0.0
        manifest_duration = float(entry.get("duration_seconds", 0) or 0)

        # Keep transcript timing aligned with clip/timeline duration so subtitle
        # and video lengths stay consistent through downstream exports.
        effective_duration = timeline_duration if timeline_duration > 0 else manifest_duration
        effective_duration = max(0.25, effective_duration)
        start = cursor
        end = start + effective_duration
        cursor = end
        segments.append(
            {
                "id": idx,
                "start": round(start, 3),
                "end": round(end, 3),
                "speaker": "SPEAKER_00",
                "text": _format_default_text(entry, idx),
                "source_segment_id": entry.get("segment_id"),
                "source_path": entry.get("normalized", ""),
                "clip_duration_seconds": round(manifest_duration, 6),
                "timeline_in_seconds": round(timeline_in, 6),
                "timeline_out_seconds": round(timeline_out if timeline_out > 0 else effective_duration, 6),
                "words": [],
            }
        )

    full_text = " ".join(s["text"] for s in segments).strip()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "pipeline_stage": "transcribe",
        "engine": {"name": "dry-run-template", "model": model, "language": language},
        "language": language,
        "segments": segments,
        "text": full_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local transcript JSON from normalized media.")
    parser.add_argument("--config", required=True, help="pipeline.config.json path")
    parser.add_argument("--repo-root", required=True, help="repo root path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    cfg = load_json(Path(args.config).resolve())
    transcript_cfg = cfg["transcription"]

    if not transcript_cfg.get("enabled", True):
        print("Transcription disabled in config; skipping stage.")
        return 0

    manifest_path = repo_root / "data/media-manifest.json"
    manifest = load_json(manifest_path)
    output_path = Path(transcript_cfg["output_transcript_json"]).resolve()

    transcript = build_dry_run_transcript(
        manifest.get("entries", []),
        language=str(transcript_cfg.get("language", "en")),
        model=str(transcript_cfg.get("model", "base")),
    )

    # Phase 1 writes a stable transcript schema and CLI wiring.
    # Full model-backed transcription is added in a follow-up phase.
    save_json(output_path, transcript)
    print(f"Transcript written: {output_path}")
    if args.dry_run:
        print("[dry-run] Transcript generated from media manifest metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
