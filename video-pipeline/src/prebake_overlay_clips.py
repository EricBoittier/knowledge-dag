#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def run_cmd(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
        .replace(",", r"\,")
    )


def _orientation_size(orientation: str) -> Tuple[int, int]:
    if orientation == "vertical":
        return (1080, 1920)
    return (1920, 1080)


def prebake_manifest(
    manifest_path: Path,
    overlay_manifest_path: Path,
    output_dir: Path,
    orientation: str,
    font_color: str = "white",
    box_color: str = "black@0.45",
) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but not found in PATH")
    manifest = load_json(manifest_path)
    overlay = load_json(overlay_manifest_path)
    subtitles = overlay.get("subtitle_segments", [])
    images = overlay.get("image_overlays", [])
    style_events = overlay.get("style_events", [])
    style_profile_map = {
        "default": {"font": "Arial", "font_color": font_color, "box_color": box_color, "font_size": 64},
        "shorts": {"font": "Montserrat", "font_color": "yellow", "box_color": "black@0.50", "font_size": 70},
        "tiktok": {"font": "Poppins", "font_color": "white", "box_color": "0x5a2ca0@0.55", "font_size": 68},
        "dialogue": {"font": "Inter", "font_color": "0x90ff90", "box_color": "black@0.55", "font_size": 66},
    }
    width, height = _orientation_size(orientation)

    out_entries: List[Dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for idx, entry in enumerate(manifest.get("entries", [])):
        src = Path(entry["normalized"]).resolve()
        subtitle_text = str(subtitles[idx]["text"]) if idx < len(subtitles) else str(entry.get("source_label", f"Clip {idx+1}"))
        profile_name = str(style_events[idx]["profile"]).lower() if idx < len(style_events) and isinstance(style_events[idx], dict) else "default"
        style = style_profile_map.get(profile_name, style_profile_map["default"])
        image_path = Path(images[idx]["asset"]).resolve() if idx < len(images) else None
        out_clip = output_dir / f"{src.stem}.{orientation}.baked.mov"
        out_clip.parent.mkdir(parents=True, exist_ok=True)

        vf_parts = [f"scale={width}:{height}:force_original_aspect_ratio=decrease", f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"]
        inputs = ["-i", str(src)]
        if image_path and image_path.exists():
            inputs.extend(["-i", str(image_path)])
            vf_parts.extend(
                [
                    "[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2[bg]".format(w=width, h=height),
                    "[1:v]scale=512:512[ov]",
                    "[bg][ov]overlay=64:H-h-64[tmpv]",
                ]
            )
            draw_src = "[tmpv]"
        else:
            draw_src = "0:v"

        text_y = "H-180" if orientation == "horizontal" else "H-260"
        draw = (
            f"drawtext=text='{_escape_drawtext(subtitle_text)}':x=(w-text_w)/2:y={text_y}:"
            f"fontsize={style['font_size']}:font={style['font']}:fontcolor={style['font_color']}:"
            f"box=1:boxcolor={style['box_color']}:boxborderw=18"
        )
        if image_path and image_path.exists():
            filter_complex = ";".join(vf_parts[2:] + [f"{draw_src}{draw}[vout]"])
            cmd = [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                filter_complex,
                "-map",
                "[vout]",
                "-map",
                "0:a?",
                "-c:v",
                "dnxhd",
                "-profile:v",
                "dnxhr_hq",
                "-pix_fmt",
                "yuv422p",
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(out_clip),
            ]
        else:
            vf = ",".join(vf_parts[:2] + [draw])
            cmd = [
                "ffmpeg",
                "-y",
                *inputs,
                "-vf",
                vf,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "dnxhd",
                "-profile:v",
                "dnxhr_hq",
                "-pix_fmt",
                "yuv422p",
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(out_clip),
            ]
        run_cmd(cmd)
        new_entry = dict(entry)
        new_entry["normalized"] = str(out_clip.resolve())
        out_entries.append(new_entry)

    out_manifest = output_dir / f"manifest.prebaked.{orientation}.json"
    write_json(out_manifest, {"input_dir": manifest.get("input_dir"), "output_dir": str(output_dir.resolve()), "entries": out_entries})
    return out_manifest
