#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-upload", action="store_true")
    args = ap.parse_args()

    if args.skip_upload:
        print("Upload skipped by flag.")
        return 0
    final_video = Path(args.project_dir).resolve() / "output" / "final.mp4"
    if args.dry_run:
        print(f"[dry-run] upload hook would publish: {final_video}")
        return 0
    print("MVP upload hook placeholder. Integrate OAuth YouTube Data API client here.")
    print(f"Target: {final_video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
