#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProbeResult:
    path: Path
    duration_seconds: float
    has_video: bool
    has_audio: bool
    video_codec: Optional[str]
    audio_codec: Optional[str]
    audio_sample_rate: Optional[int]
    audio_channels: Optional[int]
    errors: List[str]


def require_ffprobe() -> None:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is required but not found in PATH")


def probe_media(path: Path) -> Dict[str, Any]:
    require_ffprobe()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def validate_probe(path: Path, probe: Dict[str, Any]) -> ProbeResult:
    streams = probe.get("streams", [])
    fmt = probe.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration_raw = fmt.get("duration", 0.0)
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = 0.0

    errors: List[str] = []
    if video_stream is None:
        errors.append("missing_video_stream")
    if audio_stream is None:
        errors.append("missing_audio_stream")

    audio_rate: Optional[int] = None
    audio_channels: Optional[int] = None
    if audio_stream is not None:
        try:
            audio_rate = int(audio_stream.get("sample_rate"))
        except (TypeError, ValueError):
            audio_rate = None
        try:
            audio_channels = int(audio_stream.get("channels"))
        except (TypeError, ValueError):
            audio_channels = None

    return ProbeResult(
        path=path,
        duration_seconds=duration,
        has_video=video_stream is not None,
        has_audio=audio_stream is not None,
        video_codec=video_stream.get("codec_name") if video_stream else None,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        audio_sample_rate=audio_rate,
        audio_channels=audio_channels,
        errors=errors,
    )


def assert_audio_policy(result: ProbeResult, sample_rate: int, channels: int) -> List[str]:
    errors: List[str] = list(result.errors)
    if result.has_audio:
        if result.audio_sample_rate != sample_rate:
            errors.append(
                f"audio_sample_rate_mismatch(expected={sample_rate}, actual={result.audio_sample_rate})"
            )
        if result.audio_channels != channels:
            errors.append(
                f"audio_channel_mismatch(expected={channels}, actual={result.audio_channels})"
            )
    return errors
