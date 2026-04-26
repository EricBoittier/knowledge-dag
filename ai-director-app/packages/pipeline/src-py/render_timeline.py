#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    fcpxml = project_dir / "output" / "timeline_davinci_resolve.fcpxml"
    out_video = project_dir / "output" / "final.mp4"
    if args.dry_run:
        print(f"[dry-run] render hook: {fcpxml} -> {out_video}")
    else:
        print("Manual render mode in MVP. Import timeline in DaVinci and render final.mp4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
