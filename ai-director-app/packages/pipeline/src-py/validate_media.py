#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ffprobe(path: Path, selector: str, entry: str) -> str:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", selector, "-show_entries", entry, "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print("[dry-run] media validation skipped")
        return 0
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found")

    project_dir = Path(args.project_dir).resolve()
    cfg = load_json(Path(args.config).resolve())
    policy = cfg["media"]
    manifest = load_json(project_dir / "media-manifest.json")
    failures = []
    for e in manifest.get("entries", []):
        p = Path(e["normalized"])
        if not p.exists():
            failures.append(f"missing file: {p}")
            continue
        v = ffprobe(p, "v:0", "stream=codec_name")
        a = ffprobe(p, "a:0", "stream=codec_name")
        sr = ffprobe(p, "a:0", "stream=sample_rate")
        ch = ffprobe(p, "a:0", "stream=channels")
        if not v:
            failures.append(f"{p}: no video stream")
        if not a:
            failures.append(f"{p}: no audio stream")
        if sr and int(sr) != int(policy["audio_rate"]):
            failures.append(f"{p}: sample_rate {sr} != {policy['audio_rate']}")
        if ch and int(ch) != int(policy["audio_channels"]):
            failures.append(f"{p}: channels {ch} != {policy['audio_channels']}")

    if failures:
        print("Validation failed:")
        for f in failures:
            print("-", f)
        return 1
    print("Validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
