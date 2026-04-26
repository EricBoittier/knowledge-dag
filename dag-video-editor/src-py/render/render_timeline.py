#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render hook for DaVinci timeline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_json(Path(args.config).resolve())
    output_video = Path(cfg["render"]["output_video"]).resolve()
    fcpxml = Path(cfg["timeline"]["output_fcpxml"]).resolve()

    if args.dry_run:
        print(f"[dry-run] Would render timeline: {fcpxml}")
        print(f"[dry-run] Output video target: {output_video}")
        return 0

    # MVP: manual render hand-off.
    print("Render mode is manual in MVP.")
    print(f"Import this timeline in DaVinci and render to: {output_video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
