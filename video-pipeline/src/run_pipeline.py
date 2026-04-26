#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_timeline_fcpxml import build_timeline
from media_probe import assert_audio_policy, probe_media, validate_probe
from normalize_clips import normalize


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest_outputs(config_path: Path, manifest_path: Path) -> None:
    config = load_config(config_path)
    policy = config["media_policy"]
    manifest = load_config(manifest_path)

    bad = []
    for entry in manifest.get("entries", []):
        normalized = Path(entry["normalized"])
        result = validate_probe(normalized, probe_media(normalized))
        errors = assert_audio_policy(
            result,
            sample_rate=policy["audio_sample_rate"],
            channels=policy["audio_channels"],
        )
        if errors:
            bad.append((normalized, errors))

    if bad:
        details = "\n".join(f"- {p}: {errs}" for p, errs in bad)
        raise RuntimeError(f"Validation failed for normalized outputs:\n{details}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full MVP video pipeline.")
    parser.add_argument("--config", default="./project_config.json", help="Path to project config JSON")
    parser.add_argument("--input-dir", default=None, help="Optional input directory override")
    parser.add_argument("--output-dir", default=None, help="Optional output normalized directory override")
    parser.add_argument("--force", action="store_true", help="Force regeneration of normalized outputs")
    parser.add_argument(
        "--clean-old-normalized",
        action="store_true",
        help="Delete old normalized/review outputs before processing",
    )
    parser.add_argument(
        "--showcase",
        action="store_true",
        help="Generate a showcase-edited timeline (reordered/trimmed clips)",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    input_dir = Path(args.input_dir).resolve() if args.input_dir else None
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None

    print("Step A: normalize clips")
    manifest_path = normalize(
        config_path=config_path,
        input_dir_override=input_dir,
        output_dir_override=output_dir,
        force=args.force,
        clean_old_normalized=args.clean_old_normalized,
    )

    print("Step B: validate normalized outputs")
    validate_manifest_outputs(config_path, manifest_path)

    print("Step C: generate FCPXML timeline")
    config = load_config(config_path)
    timeline_output = (config_path.parent / config["paths"]["timeline_output"]).resolve()
    effective_manifest = manifest_path
    if args.showcase:
        from make_showcase_manifest import build_showcase_entries

        showcase_path = manifest_path.with_name("manifest.showcase.json")
        manifest_payload = load_config(manifest_path)
        manifest_payload["entries"] = build_showcase_entries(manifest_payload.get("entries", []))
        with showcase_path.open("w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, indent=2)
        effective_manifest = showcase_path
        print(f"Showcase edit manifest: {showcase_path}")

    build_timeline(config_path, effective_manifest, timeline_output)

    print("\nPipeline complete.")
    print(f"- Manifest: {effective_manifest}")
    print(f"- Timeline: {timeline_output}")
    print("\nNext manual step in DaVinci Resolve:")
    print("1) Import normalized media first")
    print("2) Import generated FCPXML timeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
