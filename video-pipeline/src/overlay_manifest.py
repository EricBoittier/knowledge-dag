#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class SubtitleSegment:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class ImageOverlayEvent:
    asset: str
    start: float
    end: float
    x: int
    y: int
    width: int
    height: int
    anchor: str
    sentence_index: int
    source_text: str


@dataclass(frozen=True)
class OverlayStyle:
    profile: str
    font: str
    font_size: int
    stroke: int
    safe_margin: int


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _as_non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{field_name} must be a number")


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        return value
    raise ValueError(f"{field_name} must be an integer")


def validate_subtitle_segments(segments: List[Dict[str, Any]]) -> List[SubtitleSegment]:
    out: List[SubtitleSegment] = []
    last_start = -1.0
    for idx, raw in enumerate(segments):
        if not isinstance(raw, dict):
            raise ValueError(f"subtitle_segments[{idx}] must be an object")
        text = _as_non_empty_text(raw.get("text"), f"subtitle_segments[{idx}].text")
        start = _as_float(raw.get("start"), f"subtitle_segments[{idx}].start")
        end = _as_float(raw.get("end"), f"subtitle_segments[{idx}].end")
        if start < 0:
            raise ValueError(f"subtitle_segments[{idx}] has negative start")
        if end <= start:
            raise ValueError(f"subtitle_segments[{idx}] end must be > start")
        if start < last_start:
            raise ValueError(f"subtitle_segments[{idx}] start is not monotonic")
        last_start = start
        out.append(SubtitleSegment(text=text, start=start, end=end))
    return out


def validate_image_overlays(overlays: List[Dict[str, Any]]) -> List[ImageOverlayEvent]:
    out: List[ImageOverlayEvent] = []
    last_start = -1.0
    for idx, raw in enumerate(overlays):
        if not isinstance(raw, dict):
            raise ValueError(f"image_overlays[{idx}] must be an object")
        asset = _as_non_empty_text(raw.get("asset"), f"image_overlays[{idx}].asset")
        start = _as_float(raw.get("start"), f"image_overlays[{idx}].start")
        end = _as_float(raw.get("end"), f"image_overlays[{idx}].end")
        x = _as_int(raw.get("x"), f"image_overlays[{idx}].x")
        y = _as_int(raw.get("y"), f"image_overlays[{idx}].y")
        width = _as_int(raw.get("width"), f"image_overlays[{idx}].width")
        height = _as_int(raw.get("height"), f"image_overlays[{idx}].height")
        anchor = _as_non_empty_text(raw.get("anchor"), f"image_overlays[{idx}].anchor")
        sentence_index = _as_int(raw.get("sentence_index"), f"image_overlays[{idx}].sentence_index")
        source_text = _as_non_empty_text(raw.get("source_text"), f"image_overlays[{idx}].source_text")
        if start < 0:
            raise ValueError(f"image_overlays[{idx}] has negative start")
        if end <= start:
            raise ValueError(f"image_overlays[{idx}] end must be > start")
        if width <= 0 or height <= 0:
            raise ValueError(f"image_overlays[{idx}] width/height must be positive")
        if start < last_start:
            raise ValueError(f"image_overlays[{idx}] start is not monotonic")
        last_start = start
        out.append(
            ImageOverlayEvent(
                asset=asset,
                start=start,
                end=end,
                x=x,
                y=y,
                width=width,
                height=height,
                anchor=anchor,
                sentence_index=sentence_index,
                source_text=source_text,
            )
        )
    return out


def validate_overlay_style(style: Dict[str, Any]) -> OverlayStyle:
    profile = _as_non_empty_text(style.get("profile"), "style.profile")
    font = _as_non_empty_text(style.get("font"), "style.font")
    font_size = _as_int(style.get("font_size"), "style.font_size")
    stroke = _as_int(style.get("stroke"), "style.stroke")
    safe_margin = _as_int(style.get("safe_margin"), "style.safe_margin")
    if font_size <= 0:
        raise ValueError("style.font_size must be positive")
    if stroke < 0:
        raise ValueError("style.stroke must be >= 0")
    if safe_margin < 0:
        raise ValueError("style.safe_margin must be >= 0")
    return OverlayStyle(profile=profile, font=font, font_size=font_size, stroke=stroke, safe_margin=safe_margin)


def validate_overlay_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("Overlay manifest must be an object")
    style_raw = manifest.get("style")
    segments_raw = manifest.get("subtitle_segments")
    overlays_raw = manifest.get("image_overlays")
    if not isinstance(style_raw, dict):
        raise ValueError("style must be an object")
    if not isinstance(segments_raw, list):
        raise ValueError("subtitle_segments must be an array")
    if not isinstance(overlays_raw, list):
        raise ValueError("image_overlays must be an array")
    style = validate_overlay_style(style_raw)
    segments = validate_subtitle_segments(segments_raw)
    overlays = validate_image_overlays(overlays_raw)
    style_events = manifest.get("style_events", [])
    dialogue_plan = manifest.get("dialogue_plan", [])
    if not isinstance(style_events, list):
        raise ValueError("style_events must be an array when present")
    if not isinstance(dialogue_plan, list):
        raise ValueError("dialogue_plan must be an array when present")
    return {
        "style": style.__dict__,
        "subtitle_segments": [s.__dict__ for s in segments],
        "image_overlays": [o.__dict__ for o in overlays],
        "style_events": style_events,
        "dialogue_plan": dialogue_plan,
    }
