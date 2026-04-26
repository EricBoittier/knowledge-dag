#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

MAX_VIDEO_DURATION_SECONDS = 10 * 60


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def safe_stem(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace(" ", "_")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name)
    ascii_name = re.sub(r"_+", "_", ascii_name).strip("._-")
    if not ascii_name:
        ascii_name = "clip"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{ascii_name[:72].rstrip('._-')}_{digest}"


def run(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr}")


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return 0.0
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def resolve_media_dir(config_value: str, env_name: str) -> Path:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(config_value).expanduser().resolve()


def ensure_min_free_space(target_dir: Path) -> None:
    min_free_gb_raw = os.getenv("VIDEO_MIN_FREE_GB", "25").strip()
    try:
        min_free_gb = float(min_free_gb_raw)
    except ValueError as ex:
        raise RuntimeError(f"Invalid VIDEO_MIN_FREE_GB value: {min_free_gb_raw}") from ex
    if min_free_gb <= 0:
        return
    usage = shutil.disk_usage(target_dir)
    free_gb = usage.free / (1024**3)
    if free_gb < min_free_gb:
        raise RuntimeError(
            f"Not enough free space at {target_dir} "
            f"({free_gb:.1f} GB free, require at least {min_free_gb:.1f} GB). "
            "Set VIDEO_DOWNLOAD_DIR to an external drive with more space."
        )


def download_video_with_fallback(url: str, out_tpl: Path, source: str) -> None:
    base = ["yt-dlp", "--no-playlist", "--socket-timeout", "30", "--retries", "4", "--fragment-retries", "4", "-o", str(out_tpl)]
    attempts: List[List[str]]
    if source == "youtube":
        attempts = [
            [*base, "--force-ipv4", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", url],
            [*base, "--force-ipv4", "-f", "b", url],
            [*base, "--force-ipv4", url],
        ]
    else:
        attempts = [[*base, url]]
    last_err = ""
    for cmd in attempts:
        try:
            run(cmd)
            return
        except RuntimeError as ex:
            last_err = str(ex)
            continue
    raise RuntimeError(f"yt-dlp failed after fallback attempts: {last_err[:220]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download selected clips and normalize for DaVinci.")
    parser.add_argument("--config", required=True, help="pipeline.config.json path")
    parser.add_argument("--repo-root", required=True, help="repo root path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp not found in PATH")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH")

    repo_root = Path(args.repo_root).resolve()
    cfg = load_json(Path(args.config).resolve())
    selected = load_json(repo_root / "data/selected-clips.json")
    media_cfg = cfg["media"]
    download_dir = resolve_media_dir(media_cfg["download_dir"], "VIDEO_DOWNLOAD_DIR")
    normalized_dir = resolve_media_dir(media_cfg["normalized_dir"], "VIDEO_NORMALIZED_DIR")
    download_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    ensure_min_free_space(download_dir)
    print(f"[media] download_dir={download_dir}", flush=True)
    print(f"[media] normalized_dir={normalized_dir}", flush=True)

    manifest_entries: List[Dict[str, Any]] = []
    for seg in selected.get("segments", []):
        if not seg.get("selected"):
            continue
        clip = seg["selected"][0]
        seg_id = seg["segment_id"]
        concept = seg["concept"]
        title = clip["title"]
        url = clip["url"]
        source = clip.get("source", "youtube")
        clip_duration = float(clip.get("duration_sec", 0) or 0)
        if clip_duration > MAX_VIDEO_DURATION_SECONDS:
            print(
                f"[media] skipping {seg_id}: candidate duration {clip_duration:.1f}s exceeds 10 minute limit",
                flush=True,
            )
            continue
        stem = safe_stem(f"{seg_id}_{title}")
        downloaded = download_dir / f"{stem}.%(ext)s"
        normalized = normalized_dir / f"{stem}.normalized.mov"

        if not args.dry_run:
            actual = sorted(download_dir.glob(f"{stem}.*"))
            source_file = actual[-1] if actual else None
            if normalized.exists() and source_file is not None:
                print(f"[media] reusing existing normalized clip for {seg_id}: {normalized.name}", flush=True)
            else:
                if source_file is None:
                    download_video_with_fallback(url, downloaded, source)
                    actual = sorted(download_dir.glob(f"{stem}.*"))
                    if not actual:
                        raise RuntimeError(f"No downloaded file for {seg_id}")
                    source_file = actual[-1]
                else:
                    print(f"[media] reusing existing download for {seg_id}: {source_file.name}", flush=True)
                if not normalized.exists():
                    run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(source_file),
                            "-map",
                            "0:v:0",
                            "-map",
                            "0:a:0",
                            "-c:v",
                            media_cfg["video_codec"],
                            "-profile:v",
                            media_cfg["video_profile"],
                            "-pix_fmt",
                            media_cfg["pixel_format"],
                            "-c:a",
                            media_cfg["audio_codec"],
                            "-ar",
                            str(media_cfg["audio_rate"]),
                            "-ac",
                            str(media_cfg["audio_channels"]),
                            str(normalized),
                        ]
                    )
            duration = probe_duration(normalized)
            if duration > MAX_VIDEO_DURATION_SECONDS:
                print(
                    f"[media] skipping {seg_id}: normalized duration {duration:.1f}s exceeds 10 minute limit",
                    flush=True,
                )
                continue
        else:
            source_file = Path(str(downloaded).replace("%(ext)s", "mp4"))
            duration = float(clip.get("duration_sec", 0))

        manifest_entries.append(
            {
                "segment_id": seg_id,
                "concept": concept,
                "source_url": url,
                "source_title": title,
                "source": source,
                "downloaded": str(source_file.resolve()),
                "normalized": str(normalized.resolve()),
                "duration_seconds": duration,
                "timeline": {
                    "enabled": True,
                    "label": concept,
                    "in_seconds": 0.0,
                    "out_seconds": duration,
                },
            }
        )

    save_json(
        repo_root / "data/media-manifest.json",
        {"generated_at": datetime.now(UTC).isoformat(), "entries": manifest_entries},
    )
    print(f"Media manifest written: {repo_root / 'data/media-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
