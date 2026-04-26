#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ffprobe_stream(path: Path, selector: str, entry: str) -> str:
    cmd = ["ffprobe", "-v", "error", "-select_streams", selector, "-show_entries", entry, "-of", "csv=p=0", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate normalized media manifest entries.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found in PATH")

    repo_root = Path(args.repo_root).resolve()
    cfg = load_json(Path(args.config).resolve())
    policy = cfg["media"]
    manifest_path = repo_root / "data/media-manifest.json"
    manifest = load_json(manifest_path)

    if args.dry_run:
        print("[dry-run] Skipping strict media validation.")
        return 0

    failures: List[str] = []
    for e in manifest.get("entries", []):
        p = Path(e["normalized"])
        if not p.exists():
            failures.append(f"{p}: missing file")
            continue

        video = ffprobe_stream(p, "v:0", "stream=codec_name")
        audio = ffprobe_stream(p, "a:0", "stream=codec_name")
        sr = ffprobe_stream(p, "a:0", "stream=sample_rate")
        ch = ffprobe_stream(p, "a:0", "stream=channels")

        if not video:
            failures.append(f"{p}: missing video stream")
        if not audio:
            failures.append(f"{p}: missing audio stream")
        if sr and int(sr) != int(policy["audio_rate"]):
            failures.append(f"{p}: sample rate mismatch ({sr} != {policy['audio_rate']})")
        if ch and int(ch) != int(policy["audio_channels"]):
            failures.append(f"{p}: channels mismatch ({ch} != {policy['audio_channels']})")

    if failures:
        print("Validation FAILED:")
        for f in failures:
            print(f"- {f}")
        return 1

    print("Validation PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
