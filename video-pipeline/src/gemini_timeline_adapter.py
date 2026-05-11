#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from overlay_scheduler import build_image_events
from subtitle_builder import STYLE_PRESETS


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _annotation_map(annotations_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    annotations = annotations_payload.get("annotations", [])
    return {str(a.get("segment_id")): a for a in annotations if isinstance(a, dict)}


def _script_map(script_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lines = script_payload.get("lines", [])
    return {str(l.get("segment_id")): l for l in lines if isinstance(l, dict)}


def _annotation_tokens(annotation: Dict[str, Any]) -> List[str]:
    effects = [str(x).lower() for x in annotation.get("effects", [])]
    transition = str(annotation.get("transition", "")).lower()
    lut_hint = str(annotation.get("lut_hint", "")).lower()
    return effects + [transition, lut_hint]


def _pick_style_profile(annotation: Dict[str, Any], style_rules: List[Dict[str, Any]]) -> str:
    tokens = _annotation_tokens(annotation)
    for rule in style_rules:
        profile = str(rule.get("profile", "default")).strip().lower()
        if not profile:
            continue
        if profile not in STYLE_PRESETS:
            continue
        keywords = [str(x).lower() for x in rule.get("keywords", []) if str(x).strip()]
        if not keywords:
            continue
        if any(keyword in token for keyword in keywords for token in tokens):
            return profile
    return "default"


def _sentence_split(text: str) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    out = [p.strip() for p in parts if p.strip()]
    return out if out else [cleaned]


def build_complex_overlay_payload(
    manifest_payload: Dict[str, Any],
    script_payload: Dict[str, Any],
    annotations_payload: Dict[str, Any],
    image_asset_dir: Path,
    video_width: int,
    video_height: int,
    safe_margin: int,
    overlay_width: int,
    overlay_height: int,
    anchor: str,
    checkpoint_cycle: List[str],
    style_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    script_by_id = _script_map(script_payload)
    anno_by_id = _annotation_map(annotations_payload)
    segments: List[Dict[str, Any]] = []
    style_events: List[Dict[str, Any]] = []
    dialogue_plan: List[Dict[str, Any]] = []
    cursor = 0.0
    speaker_cycle = ["narrator_a", "narrator_b", "narrator_c"]

    for idx, entry in enumerate(manifest_payload.get("entries", [])):
        timeline = entry.get("timeline", {})
        if timeline.get("enabled", True) is False:
            continue
        segment_id = f"seg_{idx + 1:03d}"
        full_duration = float(entry.get("duration_seconds", 0.0))
        in_seconds = float(timeline.get("in_seconds", 0.0))
        out_seconds = float(timeline.get("out_seconds", full_duration))
        in_seconds = max(0.0, min(in_seconds, full_duration))
        out_seconds = max(in_seconds, min(out_seconds, full_duration))
        clip_duration = max(0.01, out_seconds - in_seconds)

        script_line = script_by_id.get(segment_id, {})
        annotation = anno_by_id.get(segment_id, {})
        profile = _pick_style_profile(annotation, style_rules=style_rules)
        subtitle_text = str(script_line.get("subtitle_text") or script_line.get("text") or timeline.get("label") or f"Segment {idx+1}").strip()
        sentence_parts = _sentence_split(subtitle_text)
        sentence_duration = clip_duration / max(1, len(sentence_parts))
        for s_idx, sentence in enumerate(sentence_parts):
            start = round(cursor + sentence_duration * s_idx, 3)
            end = round(cursor + sentence_duration * (s_idx + 1), 3)
            sub_segment_id = f"{segment_id}_s{s_idx+1:02d}"
            segments.append({"segment_id": sub_segment_id, "text": sentence, "start": start, "end": end})
            style_events.append(
                {
                    "segment_id": sub_segment_id,
                    "start": start,
                    "end": end,
                    "profile": profile,
                    "transition": str(annotation.get("transition", "cross_dissolve_8f")),
                    "lut_hint": str(annotation.get("lut_hint", "neutral_doc_rec709")),
                    "effects": [str(x) for x in annotation.get("effects", [])],
                }
            )
            absolute_idx = len(dialogue_plan)
            speaker = speaker_cycle[absolute_idx % len(speaker_cycle)]
            checkpoint_dir = checkpoint_cycle[absolute_idx % len(checkpoint_cycle)] if checkpoint_cycle else ""
            dialogue_plan.append(
                {
                    "segment_id": sub_segment_id,
                    "speaker": speaker,
                    "speaker_id": absolute_idx % len(speaker_cycle),
                    "text": sentence,
                    "start": start,
                    "end": end,
                    "checkpoint_dir": checkpoint_dir,
                }
            )
        cursor += clip_duration

    image_events = build_image_events(
        subtitle_segments=segments,
        asset_dir=image_asset_dir,
        video_width=video_width,
        video_height=video_height,
        safe_margin=safe_margin,
        overlay_width=overlay_width,
        overlay_height=overlay_height,
        anchor=anchor,
        keyword_map={},
    )
    return {
        "style": STYLE_PRESETS["default"],
        "subtitle_segments": [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in segments],
        "image_overlays": image_events,
        "style_events": style_events,
        "dialogue_plan": dialogue_plan,
    }
