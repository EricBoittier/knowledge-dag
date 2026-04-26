#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from xml.etree import ElementTree as ET

from media_probe import probe_media, validate_probe


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def seconds_to_rational(seconds: float, timescale: int = 24000) -> str:
    value = int(round(seconds * timescale))
    return f"{value}/{timescale}s"


def path_to_url(path: Path) -> str:
    return path.resolve().as_uri()


def gather_assets(
    manifest_entries: List[Dict[str, Any]],
    timeline_cfg: Dict[str, Any],
) -> List[Tuple[str, Path]]:
    assets: List[Tuple[str, Path]] = []
    for i, entry in enumerate(manifest_entries, start=1):
        assets.append((f"r{i}", Path(entry["normalized"])))

    next_id = len(assets) + 1
    if timeline_cfg.get("include_intro") and timeline_cfg.get("intro_path"):
        assets.append((f"r{next_id}", Path(timeline_cfg["intro_path"])))
        next_id += 1
    if timeline_cfg.get("include_outro") and timeline_cfg.get("outro_path"):
        assets.append((f"r{next_id}", Path(timeline_cfg["outro_path"])))
        next_id += 1
    if timeline_cfg.get("include_music") and timeline_cfg.get("music_path"):
        assets.append((f"r{next_id}", Path(timeline_cfg["music_path"])))
    return assets


def build_timeline(config_path: Path, manifest_path: Path, output_path: Path) -> None:
    config = load_json(config_path)
    manifest = load_json(manifest_path)
    timeline_cfg = config["timeline"]
    entries = manifest.get("entries", [])
    if not entries:
        raise RuntimeError("Manifest has no entries. Run normalization first.")

    assets = gather_assets(entries, timeline_cfg)

    fcpxml = ET.Element("fcpxml", {"version": "1.13"})
    resources = ET.SubElement(fcpxml, "resources")
    ET.SubElement(resources, "format", {
        "id": "rFormat",
        "name": "FFVideoFormat1080p30",
        "frameDuration": "1001/30000s",
        "width": str(timeline_cfg.get("width", 1920)),
        "height": str(timeline_cfg.get("height", 1080)),
        "colorSpace": "1-1-1 (Rec. 709)",
    })

    durations: Dict[str, str] = {}
    for asset_id, media_path in assets:
        probe = validate_probe(media_path, probe_media(media_path))
        duration = seconds_to_rational(probe.duration_seconds)
        durations[asset_id] = duration
        ET.SubElement(resources, "asset", {
            "id": asset_id,
            "name": media_path.name,
            "src": path_to_url(media_path),
            "start": "0s",
            "duration": duration,
            "hasVideo": "1" if probe.has_video else "0",
            "hasAudio": "1" if probe.has_audio else "0",
            "audioSources": "1" if probe.has_audio else "0",
            "audioChannels": str(probe.audio_channels or 0),
            "audioRate": str(timeline_cfg.get("audio_rate", 48000)),
            "format": "rFormat" if probe.has_video else "",
        })

    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", {"name": "VideoPipeline"})
    project = ET.SubElement(event, "project", {"name": timeline_cfg.get("name", "AutoTimeline")})
    sequence = ET.SubElement(project, "sequence", {"format": "rFormat", "tcStart": "0s", "tcFormat": "NDF"})
    spine = ET.SubElement(sequence, "spine")

    offset_seconds = 0.0

    def add_clip(asset_ref: str, clip_name: str) -> None:
        nonlocal offset_seconds
        dur = durations[asset_ref]
        offset = seconds_to_rational(offset_seconds)
        ET.SubElement(spine, "asset-clip", {
            "name": clip_name,
            "ref": asset_ref,
            "offset": offset,
            "start": "0s",
            "duration": dur,
        })
        dval = float(dur.split("/")[0]) / float(dur.split("/")[1].replace("s", ""))
        offset_seconds += dval

    id_to_path = {asset_id: path for asset_id, path in assets}
    content_asset_ids = [f"r{i}" for i in range(1, len(entries) + 1)]
    entry_by_asset = {f"r{i}": entries[i - 1] for i in range(1, len(entries) + 1)}

    special_cursor = len(entries) + 1
    if timeline_cfg.get("include_intro") and timeline_cfg.get("intro_path"):
        intro_id = f"r{special_cursor}"
        add_clip(intro_id, id_to_path[intro_id].name)
        special_cursor += 1

    for asset_id in content_asset_ids:
        entry = entry_by_asset[asset_id]
        timeline_meta = entry.get("timeline", {})
        if timeline_meta.get("enabled", True) is False:
            continue

        full_duration = float(entry.get("duration_seconds", 0.0))
        in_seconds = float(timeline_meta.get("in_seconds", 0.0))
        out_seconds = float(timeline_meta.get("out_seconds", full_duration))
        in_seconds = max(0.0, min(in_seconds, full_duration))
        out_seconds = max(in_seconds, min(out_seconds, full_duration))
        clip_duration = max(0.01, out_seconds - in_seconds)

        offset = seconds_to_rational(offset_seconds)
        start = seconds_to_rational(in_seconds)
        duration = seconds_to_rational(clip_duration)
        clip_name = str(timeline_meta.get("label") or id_to_path[asset_id].name)
        ET.SubElement(spine, "asset-clip", {
            "name": clip_name,
            "ref": asset_id,
            "offset": offset,
            "start": start,
            "duration": duration,
        })
        offset_seconds += clip_duration

    if timeline_cfg.get("include_outro") and timeline_cfg.get("outro_path"):
        outro_id = f"r{special_cursor}"
        add_clip(outro_id, id_to_path[outro_id].name)
        special_cursor += 1

    if timeline_cfg.get("include_music") and timeline_cfg.get("music_path"):
        music_id = f"r{special_cursor}"
        ET.SubElement(spine, "asset-clip", {
            "name": id_to_path[music_id].name,
            "ref": music_id,
            "offset": "0s",
            "start": "0s",
            "duration": seconds_to_rational(offset_seconds),
            "lane": "-1",
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(fcpxml)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sequential DaVinci-compatible FCPXML timeline.")
    parser.add_argument("--config", default="./project_config.json", help="Path to config file")
    parser.add_argument("--manifest", default="", help="Path to normalization manifest (optional)")
    parser.add_argument("--output", default="", help="Path to FCPXML output (optional)")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    manifest_path = Path(args.manifest).resolve() if args.manifest else (config_path.parent / config["paths"]["manifest_path"])
    output_path = Path(args.output).resolve() if args.output else (config_path.parent / config["paths"]["timeline_output"])

    build_timeline(config_path, manifest_path, output_path)
    print(f"FCPXML written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
