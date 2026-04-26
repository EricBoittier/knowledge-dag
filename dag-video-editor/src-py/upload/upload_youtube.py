#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube upload hook (MVP dry/manual).")
    parser.add_argument("--config", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    if args.skip_upload:
        print("Upload skipped by flag.")
        return 0

    cfg = load_json(Path(args.config).resolve())
    if not cfg["upload"]["enabled"]:
        print("Upload disabled in config.upload.enabled.")
        return 0

    video = Path(cfg["render"]["output_video"]).resolve()
    title_prefix = cfg["upload"]["title_prefix"]
    description = cfg["upload"]["description_template"]

    if args.dry_run:
        print(f"[dry-run] Would upload: {video}")
        print(f"[dry-run] Title prefix: {title_prefix}")
        print(f"[dry-run] Description: {description}")
        return 0

    # Hook for real upload implementation with OAuth client.
    print("MVP upload hook: integrate YouTube Data API client here.")
    print(f"Prepared upload target: {video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
