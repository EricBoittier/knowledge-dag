#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def escape_lua_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def style_for_profile(profile: str) -> Dict[str, float]:
    p = profile.lower()
    if p == "shorts":
        return {"size": 0.075, "fill_r": 1.0, "fill_g": 0.96, "fill_b": 0.0, "fill_a": 1.0}
    if p == "tiktok":
        return {"size": 0.078, "fill_r": 1.0, "fill_g": 1.0, "fill_b": 1.0, "fill_a": 1.0}
    if p == "dialogue":
        return {"size": 0.072, "fill_r": 0.56, "fill_g": 1.0, "fill_b": 0.56, "fill_a": 1.0}
    return {"size": 0.07, "fill_r": 1.0, "fill_g": 0.96, "fill_b": 0.0, "fill_a": 1.0}


def build_fusion_settings(
    overlay_manifest_path: Path,
    template_path: Path,
    output_dir: Path,
    center_x: float = 0.5,
    center_y: float = 0.15,
) -> Path:
    payload = load_json(overlay_manifest_path)
    subtitles = payload.get("subtitle_segments", [])
    style_events = payload.get("style_events", [])
    template_text = template_path.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: List[Dict[str, Any]] = []
    for idx, seg in enumerate(subtitles):
        text = str(seg.get("text", ""))
        profile = "default"
        if idx < len(style_events) and isinstance(style_events[idx], dict):
            profile = str(style_events[idx].get("profile", "default"))
        style = style_for_profile(profile)
        out_text = template_text
        replacements = {
            "__TEXT__": escape_lua_text(text),
            "__CENTER_X__": f"{center_x:.4f}",
            "__CENTER_Y__": f"{center_y:.4f}",
            "__SIZE__": f"{style['size']:.4f}",
            "__FILL_R__": f"{style['fill_r']:.4f}",
            "__FILL_G__": f"{style['fill_g']:.4f}",
            "__FILL_B__": f"{style['fill_b']:.4f}",
            "__FILL_A__": f"{style['fill_a']:.4f}",
            "__STROKE_R__": "1.0000",
            "__STROKE_G__": "1.0000",
            "__STROKE_B__": "1.0000",
            "__STROKE_A__": "1.0000",
            "__STROKE_THICKNESS__": "0.0400",
            "__BG_R__": "0.0000",
            "__BG_G__": "0.0000",
            "__BG_B__": "0.0000",
            "__BG_A__": "1.0000",
            "__BG_THICKNESS__": "0.2200",
        }
        for k, v in replacements.items():
            out_text = out_text.replace(k, v)
        file_name = f"subtitle_{idx+1:03d}.setting"
        out_path = output_dir / file_name
        out_path.write_text(out_text, encoding="utf-8")
        entries.append(
            {
                "segment_index": idx,
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "profile": profile,
                "text": text,
                "setting_file": str(out_path.resolve()),
            }
        )
    manifest_path = output_dir / "fusion_settings_manifest.json"
    write_json(manifest_path, {"entries": entries, "template": str(template_path.resolve())})
    return manifest_path
