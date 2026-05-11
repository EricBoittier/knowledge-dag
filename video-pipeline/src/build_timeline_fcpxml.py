#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def media_src_uri(media_path: Path, fcpxml_out: Path, timeline_cfg: dict[str, Any]) -> str:
    """
    Absolute file:/// URI by default. With fcpxml_relative_media_src, use RFC 8089-style
    file:relative/path from the FCPXML directory so NLEs resolve media next to the XML.
    Uses os.path.relpath (not Path.relative_to) so sibling folders like ../output/... work.
    """
    if not timeline_cfg.get("fcpxml_relative_media_src"):
        return path_to_url(media_path)
    mp = str(media_path.expanduser().resolve())
    base = str(fcpxml_out.expanduser().resolve().parent)
    try:
        rel_s = Path(os.path.relpath(mp, base)).as_posix()
    except (ValueError, OSError):
        return path_to_url(Path(mp))
    if rel_s in (".", ""):
        return path_to_url(Path(mp))
    if not rel_s.startswith((".", "/")):
        rel_s = f"./{rel_s}"
    return f"file:{rel_s}"


def choose_entry_trim_bounds(entry: Dict[str, Any], use_broll_top_window: bool) -> tuple[float, float]:
    timeline_meta = entry.get("timeline", {})
    full_duration = float(entry.get("duration_seconds", 0.0))
    in_seconds = float(timeline_meta.get("in_seconds", 0.0))
    out_seconds = float(timeline_meta.get("out_seconds", full_duration))
    if use_broll_top_window:
        top_window = entry.get("broll_top_window") or {}
        try:
            broll_in = float(top_window.get("start_seconds"))
            broll_out = float(top_window.get("end_seconds"))
        except (TypeError, ValueError):
            broll_in, broll_out = in_seconds, out_seconds
        if broll_out > broll_in:
            in_seconds = broll_in
            out_seconds = broll_out
    in_seconds = max(0.0, min(in_seconds, full_duration))
    out_seconds = max(in_seconds, min(out_seconds, full_duration))
    return in_seconds, out_seconds


def wrap_text_lines(text: str, max_chars: int = 28, max_lines: int = 2) -> str:
    words = str(text).split()
    if not words:
        return ""
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        candidate = " ".join(current + [word]).strip()
        if len(candidate) <= max_chars or not current:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    if len(lines) <= max_lines:
        return "\n".join(lines)
    clipped = lines[: max_lines - 1]
    clipped.append(" ".join(lines[max_lines - 1 :])[:max_chars].rstrip())
    return "\n".join(clipped)


def top_left_to_fcpxml_position(
    x: float,
    y: float,
    frame_w: int,
    frame_h: int,
    overlay_w: float,
    overlay_h: float,
) -> tuple[float, float]:
    # Resolve import commonly interprets transform positions as normalized center coordinates.
    # Map top-left pixel origin to normalized center range approx [-1, 1].
    cx = x + overlay_w / 2.0
    cy = y + overlay_h / 2.0
    px = (cx / max(1.0, float(frame_w))) * 2.0 - 1.0
    py = 1.0 - (cy / max(1.0, float(frame_h))) * 2.0
    return (px, py)


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


def build_timeline(
    config_path: Path,
    manifest_path: Path,
    output_path: Path,
    overlay_manifest_path: Path | None = None,
    dialogue_audio_path: Path | None = None,
    timeline_overrides: dict[str, Any] | None = None,
) -> None:
    config = load_json(config_path)
    manifest = load_json(manifest_path)
    timeline_cfg = dict(config.get("timeline") or {})
    if timeline_overrides:
        timeline_cfg.update(timeline_overrides)
    config["timeline"] = timeline_cfg
    entries = manifest.get("entries", [])
    if not entries:
        raise RuntimeError("Manifest has no entries. Run normalization first.")
    use_broll_top_window = bool(config.get("timeline", {}).get("use_broll_top_window", False))

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
            "src": media_src_uri(media_path, output_path, timeline_cfg),
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

    overlay_payload: Dict[str, Any] = {}
    overlay_markers: List[Dict[str, Any]] = []
    overlay_images: List[Dict[str, Any]] = []
    if overlay_manifest_path and overlay_manifest_path.exists():
        overlay_payload = load_json(overlay_manifest_path)
        overlay_markers = list(overlay_payload.get("subtitle_segments", []))
        overlay_images = list(overlay_payload.get("image_overlays", []))

    # Title effect so Resolve imports text as actual title track elements.
    title_effect_id = "rTitleEffect"
    ET.SubElement(
        resources,
        "effect",
        {
            "id": title_effect_id,
            "name": "Basic Title",
            "uid": ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti",
        },
    )

    image_asset_ids: Dict[str, str] = {}
    image_id_cursor = len(assets) + 10
    for image in overlay_images:
        image_src = str(image.get("asset", "")).strip()
        if not image_src or image_src in image_asset_ids:
            continue
        image_path = Path(image_src)
        if not image_path.exists():
            continue
        image_asset_id = f"r{image_id_cursor}"
        image_id_cursor += 1
        image_asset_ids[image_src] = image_asset_id
        ET.SubElement(
            resources,
            "asset",
            {
                "id": image_asset_id,
                "name": image_path.name,
                "src": media_src_uri(image_path, output_path, timeline_cfg),
                "start": "0s",
                "duration": seconds_to_rational(max(0.01, float(image.get("end", 0.0)) - float(image.get("start", 0.0)))),
                "hasVideo": "1",
                "hasAudio": "0",
                "audioSources": "0",
                "audioChannels": "0",
                "audioRate": str(timeline_cfg.get("audio_rate", 48000)),
                "format": "rFormat",
            },
        )

    for asset_id in content_asset_ids:
        entry = entry_by_asset[asset_id]
        timeline_meta = entry.get("timeline", {})
        if timeline_meta.get("enabled", True) is False:
            continue

        in_seconds, out_seconds = choose_entry_trim_bounds(entry, use_broll_top_window=use_broll_top_window)
        clip_duration = max(0.01, out_seconds - in_seconds)

        offset = seconds_to_rational(offset_seconds)
        start = seconds_to_rational(in_seconds)
        duration = seconds_to_rational(clip_duration)
        clip_name = str(timeline_meta.get("label") or id_to_path[asset_id].name)
        clip_element = ET.SubElement(spine, "asset-clip", {
            "name": clip_name,
            "ref": asset_id,
            "offset": offset,
            "start": start,
            "duration": duration,
        })
        clip_start = offset_seconds
        clip_end = offset_seconds + clip_duration
        for marker in overlay_markers:
            marker_start = float(marker.get("start", 0.0))
            marker_end = float(marker.get("end", marker_start))
            if marker_start < clip_start or marker_start >= clip_end:
                continue
            marker_local = marker_start - clip_start + in_seconds
            marker_duration = max(0.01, marker_end - marker_start)
            ET.SubElement(
                clip_element,
                "marker",
                {
                    "start": seconds_to_rational(marker_local),
                    "duration": seconds_to_rational(marker_duration),
                    "value": str(marker.get("text", "subtitle")),
                },
            )
        for marker in list(entry.get("broll_markers", [])):
            marker_start = float(marker.get("t_seconds", 0.0))
            if marker_start < in_seconds or marker_start >= out_seconds:
                continue
            marker_local = marker_start
            ET.SubElement(
                clip_element,
                "marker",
                {
                    "start": seconds_to_rational(marker_local),
                    "duration": seconds_to_rational(0.1),
                    "value": str(marker.get("label", "broll")),
                },
            )
        offset_seconds += clip_duration

    # Add subtitle/title elements on a dedicated upper lane so Resolve imports editable text track elements.
    for idx, marker in enumerate(overlay_markers):
        marker_start = float(marker.get("start", 0.0))
        marker_end = float(marker.get("end", marker_start))
        marker_duration = max(0.01, marker_end - marker_start)
        wrapped_text = wrap_text_lines(str(marker.get("text", "")), max_chars=28, max_lines=2)
        title = ET.SubElement(
            spine,
            "title",
            {
                "name": f"Subtitle {idx+1}",
                "ref": title_effect_id,
                "lane": "1",
                "offset": seconds_to_rational(marker_start),
                "start": "0s",
                "duration": seconds_to_rational(marker_duration),
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Title Background Height",
                "value": "0.62",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Background Opacity",
                "value": "1",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Title Background Opacity",
                "value": "1",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Background Width",
                "value": "1",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Background Color",
                "value": "0 0 0 1",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Background",
                "value": "1",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Position",
                "value": "0 -0.78",
            },
        )
        ET.SubElement(
            title,
            "param",
            {
                "name": "Y Position",
                "value": "-0.78",
            },
        )
        main_style_id = f"ts_main_{idx+1}"
        ET.SubElement(
            title,
            "text-style-def",
            {
                "id": main_style_id,
            },
        )
        style_ref = title.find("text-style-def")
        if style_ref is not None:
            ET.SubElement(
                style_ref,
                "text-style",
                {
                    "font": "Arial",
                    "fontSize": "64",
                    "fontColor": "1 0.96 0.0 1",
                    "strokeColor": "1 1 1 1",
                    "strokeWidth": "2",
                    "backgroundColor": "0 0 0 1",
                    "background": "1",
                    "lineSpacing": "1",
                    "alignment": "1",
                    "bold": "1",
                },
            )
        text_el = ET.SubElement(title, "text")
        text_style = ET.SubElement(text_el, "text-style", {"ref": main_style_id})
        text_style.text = wrapped_text
        # Keyframe experiment metadata for title motion (Resolve may import fully or partially).
        kf = ET.SubElement(title, "adjust-transform", {"position": "0 0", "scale": "1 1", "rotation": "0"})
        kf_anim = ET.SubElement(kf, "keyframeAnimation")
        ET.SubElement(kf_anim, "keyframe", {"time": "0s", "value": "0 0 0"})
        ET.SubElement(kf_anim, "keyframe", {"time": seconds_to_rational(max(0.01, marker_duration * 0.5)), "value": "18 -10 2"})
        ET.SubElement(kf_anim, "keyframe", {"time": seconds_to_rational(marker_duration), "value": "0 0 -1"})

        # Karaoke-style highlighted word lane: one short title per word, staggered across segment duration.
        words = [w for w in str(marker.get("text", "")).split() if w]
        if words:
            word_dur = max(0.06, marker_duration / len(words))
            for widx, word in enumerate(words):
                w_start = marker_start + widx * word_dur
                w_end = min(marker_end, w_start + word_dur)
                w_duration = max(0.04, w_end - w_start)
                w_title = ET.SubElement(
                    spine,
                    "title",
                    {
                        "name": f"Karaoke {idx+1}.{widx+1}",
                        "ref": title_effect_id,
                        "lane": "3",
                        "offset": seconds_to_rational(w_start),
                        "start": "0s",
                        "duration": seconds_to_rational(w_duration),
                    },
                )
                ET.SubElement(w_title, "param", {"name": "Background Height", "value": "0.26"})
                ET.SubElement(w_title, "param", {"name": "Background Opacity", "value": "1"})
                ET.SubElement(w_title, "param", {"name": "Title Background Height", "value": "0.26"})
                ET.SubElement(w_title, "param", {"name": "Title Background Opacity", "value": "1"})
                ET.SubElement(w_title, "param", {"name": "Background Color", "value": "0 0 0 1"})
                ET.SubElement(w_title, "param", {"name": "Background", "value": "1"})
                ET.SubElement(w_title, "param", {"name": "Position", "value": "0 -0.90"})
                ET.SubElement(w_title, "param", {"name": "Y Position", "value": "-0.90"})
                w_style_def = ET.SubElement(w_title, "text-style-def", {"id": f"tsK{idx+1}_{widx+1}"})
                ET.SubElement(
                    w_style_def,
                    "text-style",
                    {
                        "font": "Arial",
                        "fontSize": "58",
                        "fontColor": "1 1 0.2 1",
                        "strokeColor": "1 1 1 1",
                        "strokeWidth": "2",
                        "backgroundColor": "0 0 0 1",
                        "alignment": "1",
                        "bold": "1",
                    },
                )
                w_text = ET.SubElement(w_title, "text")
                w_text_style = ET.SubElement(w_text, "text-style", {"ref": f"tsK{idx+1}_{widx+1}"})
                w_text_style.text = word

    for image in overlay_images:
        image_src = str(image.get("asset", "")).strip()
        image_asset_id = image_asset_ids.get(image_src)
        if not image_asset_id:
            continue
        start = float(image.get("start", 0.0))
        end = float(image.get("end", start))
        duration = max(0.01, end - start)
        image_clip = ET.SubElement(
            spine,
            "asset-clip",
            {
                "name": Path(image_src).name,
                "ref": image_asset_id,
                "lane": "2",
                "offset": seconds_to_rational(start),
                "start": "0s",
                "duration": seconds_to_rational(duration),
            },
        )
        # Keyframe experiment: gentle motion on overlay image clip.
        x = float(image.get("x", 0))
        y = float(image.get("y", 0))
        ow = float(image.get("width", 512))
        oh = float(image.get("height", 512))
        px, py = top_left_to_fcpxml_position(
            x=x,
            y=y,
            frame_w=int(timeline_cfg.get("width", 1920)),
            frame_h=int(timeline_cfg.get("height", 1080)),
            overlay_w=ow,
            overlay_h=oh,
        )
        adjust = ET.SubElement(
            image_clip,
            "adjust-transform",
            {
                "position": f"{px:.2f} {py:.2f}",
                "scale": "1 1",
                "rotation": "0",
            },
        )
        kfa = ET.SubElement(adjust, "keyframeAnimation")
        ET.SubElement(kfa, "keyframe", {"time": "0s", "value": f"{px:.2f} {py:.2f} 0"})
        ET.SubElement(
            kfa,
            "keyframe",
            {
                "time": seconds_to_rational(max(0.01, duration * 0.5)),
                "value": f"{px + 0.04:.2f} {py + 0.03:.2f} 3",
            },
        )
        ET.SubElement(kfa, "keyframe", {"time": seconds_to_rational(duration), "value": f"{px:.2f} {py:.2f} -2"})

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

    if dialogue_audio_path and dialogue_audio_path.exists():
        dialogue_id = f"r{special_cursor + 1}"
        dialogue_probe = validate_probe(dialogue_audio_path, probe_media(dialogue_audio_path))
        ET.SubElement(resources, "asset", {
            "id": dialogue_id,
            "name": dialogue_audio_path.name,
            "src": media_src_uri(dialogue_audio_path, output_path, timeline_cfg),
            "start": "0s",
            "duration": seconds_to_rational(dialogue_probe.duration_seconds),
            "hasVideo": "0",
            "hasAudio": "1",
            "audioSources": "1",
            "audioChannels": str(dialogue_probe.audio_channels or 1),
            "audioRate": str(timeline_cfg.get("audio_rate", 48000)),
            "format": "",
        })
        ET.SubElement(spine, "asset-clip", {
            "name": dialogue_audio_path.name,
            "ref": dialogue_id,
            "offset": "0s",
            "start": "0s",
            "duration": seconds_to_rational(offset_seconds),
            "lane": "-2",
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
