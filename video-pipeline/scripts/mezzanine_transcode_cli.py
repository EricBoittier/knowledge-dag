#!/usr/bin/env python3
"""Transcode any video to DaVinci mezzanine MOV (DNxHR HQ + PCM), matching normalize_clips / README."""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _load_style_transfer_video(repo_root: Path):
    path = repo_root / "video-pipeline/scripts/style_transfer_video.py"
    spec = importlib.util.spec_from_file_location("style_transfer_video", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="Source video (e.g. stylized H.264 MP4)")
    p.add_argument("output", type=Path, help="Destination .mov")
    p.add_argument(
        "--fps",
        default="30",
        help="Output -r for ffmpeg (e.g. 8, 30, 24000/1001); default probes r_frame_rate if --fps=probe",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="project_config.json (default: video-pipeline/project_config.json)",
    )
    args = p.parse_args()
    repo_root = Path(__file__).resolve().parent.parent.parent
    stv = _load_style_transfer_video(repo_root)
    cfg = args.config or (repo_root / "video-pipeline/project_config.json")
    pol = stv.load_davinci_media_policy(cfg if cfg.is_file() else None)
    fps: str | float = args.fps
    if str(fps) == "probe":
        import subprocess

        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "default=nw=1:nk=1",
                str(args.input),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        fps = (r.stdout or "").strip() or "30/1"
        if fps == "N/A":
            fps = "30/1"
    stv.transcode_to_davinci_mezzanine_mov(
        args.input.expanduser().resolve(),
        args.output.expanduser().resolve(),
        policy=pol,
        output_fps=fps,
        ffmpeg_overwrite_flag="-y",
        quiet=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
