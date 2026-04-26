#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def build_showcase_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Reorder by duration descending to feel more "edited".
    sorted_entries = sorted(entries, key=lambda e: float(e.get("duration_seconds", 0.0)), reverse=True)

    out: List[Dict[str, Any]] = []
    for idx, entry in enumerate(sorted_entries):
        duration = float(entry.get("duration_seconds", 0.0))
        if duration <= 0.2:
            timeline = {
                "enabled": True,
                "label": f"Shot {idx+1}",
                "in_seconds": 0.0,
                "out_seconds": duration,
            }
        else:
            # Alternate trims to create visible editorial variation.
            trim_start = 0.2 * (idx % 3)
            trim_end_pad = 0.3 * ((idx + 1) % 3)
            in_seconds = min(trim_start, max(0.0, duration - 0.1))
            out_seconds = max(in_seconds + 0.1, duration - trim_end_pad)
            out_seconds = min(out_seconds, duration)
            timeline = {
                "enabled": True,
                "label": f"Shot {idx+1}",
                "in_seconds": round(in_seconds, 3),
                "out_seconds": round(out_seconds, 3),
            }

        e = dict(entry)
        e["timeline"] = timeline
        out.append(e)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a showcase-edited manifest from normalization output.")
    parser.add_argument("--manifest", required=True, help="Path to base manifest.json")
    parser.add_argument("--output", required=True, help="Path to showcase manifest output")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    out_path = Path(args.output).resolve()
    manifest = load_json(manifest_path)
    entries = manifest.get("entries", [])
    if not entries:
        raise RuntimeError("Manifest has no entries")

    showcase = dict(manifest)
    showcase["entries"] = build_showcase_entries(entries)
    save_json(out_path, showcase)
    print(f"Showcase manifest written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
