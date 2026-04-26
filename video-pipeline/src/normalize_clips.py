#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from media_probe import assert_audio_policy, probe_media, validate_probe

SUPPORTED_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


def safe_stem(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace(" ", "_")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name)
    ascii_name = re.sub(r"_+", "_", ascii_name).strip("._-")
    if not ascii_name:
        ascii_name = "clip"
    # Keep names manageable and collision-safe.
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    ascii_name = ascii_name[:72].rstrip("._-")
    return f"{ascii_name}_{digest}"


def load_config(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_inputs(input_dir: Path) -> List[Path]:
    files = [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    return sorted(files)


def build_ffmpeg_cmd(src: Path, dst: Path, policy: Dict[str, Any]) -> List[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        policy["video_codec"],
        "-profile:v",
        policy["video_profile"],
        "-pix_fmt",
        policy["pixel_format"],
        "-r",
        str(policy["frame_rate"]),
        "-c:a",
        policy["audio_codec"],
        "-ar",
        str(policy["audio_sample_rate"]),
        "-ac",
        str(policy["audio_channels"]),
        str(dst),
    ]


def run_cmd(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + proc.stdout
            + "\nSTDERR:\n"
            + proc.stderr
        )


def create_review_output(src: Path, dst: Path, review_policy: Dict[str, Any]) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        review_policy["video_codec"],
        "-crf",
        str(review_policy["video_crf"]),
        "-preset",
        str(review_policy["video_preset"]),
        "-c:a",
        review_policy["audio_codec"],
        str(dst),
    ]
    run_cmd(cmd)


def normalize(
    config_path: Path,
    input_dir_override: Path | None,
    output_dir_override: Path | None,
    force: bool,
    clean_old_normalized: bool,
) -> Path:
    config = load_config(config_path)
    paths = config["paths"]
    media_policy = config["media_policy"]
    review_policy = config.get("review_policy", {"enabled": False})

    input_dir = input_dir_override or (config_path.parent / paths["input_dir"])
    output_dir = output_dir_override or (config_path.parent / paths["normalized_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if clean_old_normalized:
        for old_file in output_dir.glob("*.normalized.mov"):
            old_file.unlink(missing_ok=True)
        for old_file in output_dir.glob("*.review.mp4"):
            old_file.unlink(missing_ok=True)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but not found in PATH")

    manifest_entries: List[Dict[str, Any]] = []
    inputs = iter_inputs(input_dir)
    if not inputs:
        raise RuntimeError(f"No supported media files found in input dir: {input_dir}")

    for src in inputs:
        original_base_name = src.stem
        base_name = safe_stem(original_base_name)
        mov_out = output_dir / f"{base_name}.normalized.mov"
        review_out = output_dir / f"{base_name}.review.{review_policy.get('container', 'mp4')}"

        if mov_out.exists() and not force:
            probe = validate_probe(mov_out, probe_media(mov_out))
            errors = assert_audio_policy(
                probe,
                sample_rate=media_policy["audio_sample_rate"],
                channels=media_policy["audio_channels"],
            )
            manifest_entries.append(
                {
                    "source": str(src.resolve()),
                    "normalized": str(mov_out.resolve()),
                    "review": str(review_out.resolve()) if review_out.exists() else None,
                    "source_label": original_base_name,
                    "duration_seconds": probe.duration_seconds,
                    "video_codec": probe.video_codec,
                    "audio_codec": probe.audio_codec,
                    "timeline": {
                    "enabled": True,
                        "label": original_base_name,
                    "in_seconds": 0.0,
                    "out_seconds": probe.duration_seconds,
                },
                    "errors": errors,
                    "skipped_existing": True,
                }
            )
            continue

        run_cmd(build_ffmpeg_cmd(src, mov_out, media_policy))
        if review_policy.get("enabled", False):
            create_review_output(mov_out, review_out, review_policy)

        probe = validate_probe(mov_out, probe_media(mov_out))
        errors = assert_audio_policy(
            probe,
            sample_rate=media_policy["audio_sample_rate"],
            channels=media_policy["audio_channels"],
        )
        manifest_entries.append(
            {
                "source": str(src.resolve()),
                "normalized": str(mov_out.resolve()),
                "review": str(review_out.resolve()) if review_out.exists() else None,
                "source_label": original_base_name,
                "duration_seconds": probe.duration_seconds,
                "video_codec": probe.video_codec,
                "audio_codec": probe.audio_codec,
                "timeline": {
                    "enabled": True,
                    "label": original_base_name,
                    "in_seconds": 0.0,
                    "out_seconds": probe.duration_seconds,
                },
                "errors": errors,
                "skipped_existing": False,
            }
        )

    manifest_path = config_path.parent / paths["manifest_path"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "input_dir": str(input_dir.resolve()),
                "output_dir": str(output_dir.resolve()),
                "entries": manifest_entries,
            },
            f,
            indent=2,
        )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize clips to DaVinci-safe mezzanine outputs.")
    parser.add_argument("--config", default="./project_config.json", help="Path to project config JSON")
    parser.add_argument("--input-dir", default=None, help="Optional input directory override")
    parser.add_argument("--output-dir", default=None, help="Optional normalized output directory override")
    parser.add_argument("--force", action="store_true", help="Recreate outputs even if they already exist")
    parser.add_argument(
        "--clean-old-normalized",
        action="store_true",
        help="Delete old *.normalized.mov/*.review.mp4 outputs before processing",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    input_dir = Path(args.input_dir).resolve() if args.input_dir else None
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None

    manifest_path = normalize(
        config_path=config_path,
        input_dir_override=input_dir,
        output_dir_override=output_dir,
        force=args.force,
        clean_old_normalized=args.clean_old_normalized,
    )
    print(f"Manifest written: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
