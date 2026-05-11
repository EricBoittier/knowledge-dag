#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Any

from overlay_manifest import validate_subtitle_segments, write_json

STYLE_PRESETS = {
    "default": {
        "profile": "default",
        "font": "Arial",
        "font_size": 56,
        "stroke": 3,
        "safe_margin": 64,
        "primary_colour": "&H0000F5FF",
        "outline_colour": "&H00FFFFFF",
        "back_colour": "&HAA000000",
    },
    "shorts": {
        "profile": "shorts",
        "font": "Montserrat",
        "font_size": 62,
        "stroke": 5,
        "safe_margin": 72,
        "primary_colour": "&H0000F5FF",
        "outline_colour": "&H00FFFFFF",
        "back_colour": "&HAA000000",
    },
    "tiktok": {
        "profile": "tiktok",
        "font": "Poppins",
        "font_size": 64,
        "stroke": 4,
        "safe_margin": 84,
        "primary_colour": "&H00FFFFFF",
        "outline_colour": "&H00FFFFFF",
        "back_colour": "&HAA000000",
    },
    "dialogue": {
        "profile": "dialogue",
        "font": "Inter",
        "font_size": 58,
        "stroke": 4,
        "safe_margin": 78,
        "primary_colour": "&H0090FF90",
        "outline_colour": "&H00FFFFFF",
        "back_colour": "&HAA000000",
    },
}


def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02}:{secs:05.2f}"


def format_srt_time(seconds: float) -> str:
    whole = int(seconds)
    ms = int(round((seconds - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def wrap_caption(text: str, max_chars_per_line: int, max_lines_per_cue: int) -> str:
    words = text.split()
    if not words:
        return ""
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        candidate = " ".join(current + [word]).strip()
        if len(candidate) <= max_chars_per_line or not current:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    if len(lines) <= max_lines_per_cue:
        return "\\N".join(lines)
    visible = lines[: max_lines_per_cue - 1]
    tail = " ".join(lines[max_lines_per_cue - 1 :])
    visible.append(tail[: max_chars_per_line].rstrip())
    return "\\N".join(visible)


def _ass_escape_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def _build_karaoke_text(text: str, start: float, end: float, max_chars_per_line: int, max_lines_per_cue: int) -> str:
    wrapped = wrap_caption(text, max_chars_per_line=max_chars_per_line, max_lines_per_cue=max_lines_per_cue)
    words = [w for w in wrapped.split() if w]
    if not words:
        return ""
    total_cs = max(1, int(round((end - start) * 100)))
    per_word = max(1, total_cs // len(words))
    remainder = total_cs - per_word * len(words)
    out: List[str] = []
    for idx, word in enumerate(words):
        dur = per_word + (1 if idx < remainder else 0)
        out.append(r"{\k" + str(dur) + "}" + _ass_escape_text(word))
    return " ".join(out)


def _build_styles_block(style_set: Dict[str, Dict[str, Any]]) -> str:
    lines: List[str] = []
    for name, profile in style_set.items():
        lines.append(
            "Style: {name},{font},{font_size},{primary},&H000000FF,{outline},{back},-1,0,0,0,100,100,0,0,1,{stroke},0,2,40,40,{safe_margin},1".format(
                name=name,
                font=profile["font"],
                font_size=profile["font_size"],
                primary=profile.get("primary_colour", "&H00FFFFFF"),
                outline=profile.get("outline_colour", "&H00000000"),
                back=profile.get("back_colour", "&H66000000"),
                stroke=profile["stroke"],
                safe_margin=profile["safe_margin"],
            )
        )
    return "\n".join(lines)


def build_ass(
    segments: List[Dict[str, float | str]],
    profile: Dict[str, int | str],
    max_chars_per_line: int,
    max_lines_per_cue: int,
    style_events: List[Dict[str, Any]] | None = None,
) -> str:
    style_set: Dict[str, Dict[str, Any]] = {"Default": dict(profile)}
    event_style_names: List[str] = []
    if style_events:
        for idx, ev in enumerate(style_events):
            profile_name = str(ev.get("profile", "default")).lower()
            preset = dict(STYLE_PRESETS.get(profile_name, STYLE_PRESETS["default"]))
            style_name = f"Profile{idx+1}"
            style_set[style_name] = preset
            event_style_names.append(style_name)
    styles_block = _build_styles_block(style_set)
    ass = """[Script Info]
Title: Overlay Captions
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles_block}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".format(
        styles_block=styles_block
    )
    for idx, seg in enumerate(segments):
        style_name = event_style_names[idx] if idx < len(event_style_names) else "Default"
        text = _build_karaoke_text(
            str(seg["text"]),
            start=float(seg["start"]),
            end=float(seg["end"]),
            max_chars_per_line=max_chars_per_line,
            max_lines_per_cue=max_lines_per_cue,
        )
        # Ensure explicit hard line breaks remain in ASS text for readable subtitle lines.
        text = text.replace(" \\N ", r"\N").replace("\\N ", r"\N").replace(" \\N", r"\N")
        ass += f"Dialogue: 0,{format_ass_time(float(seg['start']))},{format_ass_time(float(seg['end']))},{style_name},,0,0,0,,{text}\n"
    return ass


def build_srt(segments: List[Dict[str, float | str]], max_chars_per_line: int, max_lines_per_cue: int) -> str:
    lines: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        text = wrap_caption(str(seg["text"]), max_chars_per_line=max_chars_per_line, max_lines_per_cue=max_lines_per_cue).replace("\\N", "\n")
        lines.extend(
            [
                str(idx),
                f"{format_srt_time(float(seg['start']))} --> {format_srt_time(float(seg['end']))}",
                text,
                "",
            ]
        )
    return "\n".join(lines)


def write_subtitles(
    subtitle_segments: List[Dict[str, float | str]],
    output_dir: Path,
    profile_name: str,
    max_chars_per_line: int,
    max_lines_per_cue: int,
    style_events: List[Dict[str, Any]] | None = None,
) -> Dict[str, str]:
    segments = [s.__dict__ for s in validate_subtitle_segments(subtitle_segments)]
    profile = STYLE_PRESETS.get(profile_name, STYLE_PRESETS["default"])
    output_dir.mkdir(parents=True, exist_ok=True)
    ass_path = output_dir / "subtitles.ass"
    srt_path = output_dir / "subtitles.srt"
    ass_path.write_text(
        build_ass(
            segments,
            profile,
            max_chars_per_line,
            max_lines_per_cue,
            style_events=style_events,
        ),
        encoding="utf-8",
    )
    srt_path.write_text(build_srt(segments, max_chars_per_line, max_lines_per_cue), encoding="utf-8")
    write_json(output_dir / "subtitle_profile.json", profile)
    return {"ass": str(ass_path.resolve()), "srt": str(srt_path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ASS/SRT files from subtitle segments JSON")
    parser.add_argument("--segments-json", required=True, help="Path to subtitle segments JSON")
    parser.add_argument("--output-dir", required=True, help="Output directory for subtitles")
    parser.add_argument("--profile", default="default", choices=sorted(STYLE_PRESETS.keys()))
    parser.add_argument("--max-chars-per-line", type=int, default=36)
    parser.add_argument("--max-lines-per-cue", type=int, default=2)
    args = parser.parse_args()

    from overlay_manifest import load_json

    payload = load_json(Path(args.segments_json).resolve())
    segments = payload["subtitle_segments"] if "subtitle_segments" in payload else payload
    write_subtitles(
        subtitle_segments=segments,
        output_dir=Path(args.output_dir).resolve(),
        profile_name=args.profile,
        max_chars_per_line=args.max_chars_per_line,
        max_lines_per_cue=args.max_lines_per_cue,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
