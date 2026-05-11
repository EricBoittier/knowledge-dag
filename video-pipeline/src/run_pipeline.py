#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import uuid
from pathlib import Path

from build_timeline_fcpxml import build_timeline
from compose_overlay_preview import compose_preview
from fusion_setting_builder import build_fusion_settings
from gemini_broll_evaluator import evaluate_manifest_broll_fit
from gemini_timeline_adapter import build_complex_overlay_payload, load_json as load_json_generic, write_json as write_json_generic
from media_probe import assert_audio_policy, probe_media, validate_probe
from normalize_clips import normalize
from overlay_manifest import validate_overlay_manifest, write_json
from overlay_scheduler import build_image_events
from prebake_overlay_clips import prebake_manifest
from subtitle_builder import STYLE_PRESETS, write_subtitles


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def build_timeline_variants(
    config_path: Path,
    manifest_path: Path,
    base_output_path: Path,
    overlay_manifest_path: Path | None,
    variants: list[str],
    variant_manifest_paths: dict[str, Path] | None = None,
    dialogue_audio_path: Path | None = None,
) -> list[Path]:
    config = load_config(config_path)
    outputs: list[Path] = []
    variant_map = {
        "horizontal": (1920, 1080),
        "vertical": (1080, 1920),
    }
    for variant in variants:
        size = variant_map.get(variant)
        if not size:
            continue
        width, height = size
        cfg = dict(config)
        cfg["timeline"] = dict(config.get("timeline", {}))
        cfg["timeline"]["width"] = width
        cfg["timeline"]["height"] = height
        base_name = str(cfg["timeline"].get("name", "AutoTimeline"))
        run_tag = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        nonce = uuid.uuid4().hex[:6]
        cfg["timeline"]["name"] = f"{base_name}-{variant}-{run_tag}-{nonce}"
        out_path = base_output_path.with_name(f"{base_output_path.stem}.{variant}{base_output_path.suffix}")
        tmp_cfg_path = base_output_path.parent / f".tmp.timeline.{variant}.json"
        with tmp_cfg_path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        try:
            active_manifest = manifest_path
            if variant_manifest_paths and variant in variant_manifest_paths:
                active_manifest = variant_manifest_paths[variant]
            build_timeline(
                tmp_cfg_path,
                active_manifest,
                out_path,
                overlay_manifest_path=overlay_manifest_path,
                dialogue_audio_path=dialogue_audio_path,
            )
        finally:
            tmp_cfg_path.unlink(missing_ok=True)
        outputs.append(out_path)
    return outputs


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


def build_subtitle_segments_from_manifest(manifest: dict) -> list[dict]:
    segments: list[dict] = []
    cursor = 0.0
    for idx, entry in enumerate(manifest.get("entries", [])):
        timeline = entry.get("timeline", {})
        if timeline.get("enabled", True) is False:
            continue
        full_duration = float(entry.get("duration_seconds", 0.0))
        start_in = float(timeline.get("in_seconds", 0.0))
        end_out = float(timeline.get("out_seconds", full_duration))
        start_in = max(0.0, min(start_in, full_duration))
        end_out = max(start_in, min(end_out, full_duration))
        clip_duration = max(0.01, end_out - start_in)
        label = str(timeline.get("label") or entry.get("source_label") or f"Clip {idx+1}")
        segments.append(
            {
                "text": label,
                "start": round(cursor, 3),
                "end": round(cursor + clip_duration, 3),
            }
        )
        cursor += clip_duration
    return segments


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
    parser.add_argument("--with-overlays", action="store_true", help="Generate overlay manifest + subtitle artifacts")
    parser.add_argument("--with-preview", action="store_true", help="Compose FFmpeg preview with overlays/subtitles")
    parser.add_argument("--gemini-project-dir", default="", help="ai-director-app project dir with script-lines/edit-annotations")
    parser.add_argument(
        "--timeline-variants",
        default="horizontal",
        help="Comma-separated output variants: horizontal,vertical",
    )
    parser.add_argument("--generate-dialogue-audio", action="store_true", help="Generate multi-character dialogue WAV")
    parser.add_argument("--prebake-overlays", action="store_true", help="Prebake text/image overlays into normalized clips")
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

    config = load_config(config_path)
    gemini_project_dir = Path(args.gemini_project_dir).resolve() if args.gemini_project_dir else None
    judge_result = evaluate_manifest_broll_fit(
        manifest_path=manifest_path,
        cfg=config,
        gemini_project_dir=gemini_project_dir,
    )
    if judge_result.get("enabled"):
        print(
            "Step B2: Gemini B-roll judge "
            f"(included={judge_result.get('included', 0)}, excluded={judge_result.get('excluded', 0)})"
        )

    print("Step C: generate FCPXML timeline")
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

    variant_names = [x.strip().lower() for x in args.timeline_variants.split(",") if x.strip()]
    if not variant_names:
        variant_names = ["horizontal"]

    overlay_manifest_path: Path | None = None
    overlay_subtitles_ass: Path | None = None
    image_events_path: Path | None = None
    if args.with_overlays or args.with_preview:
        print("Step D: generate subtitle + overlay artifacts")
        overlays_cfg = config.get("overlays", {})
        # Keep subtitle line length safe for chosen orientation(s).
        if "vertical" in variant_names and "horizontal" in variant_names:
            overlays_cfg["max_chars_per_line"] = min(int(overlays_cfg.get("max_chars_per_line", 36)), 24)
        elif "vertical" in variant_names:
            overlays_cfg["max_chars_per_line"] = min(int(overlays_cfg.get("max_chars_per_line", 36)), 22)
        overlay_paths = overlays_cfg.get("paths", {})
        output_dir = (config_path.parent / overlay_paths.get("output_dir", "./output/overlays")).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_payload = load_config(effective_manifest)
        profile_name = str(overlays_cfg.get("subtitle_profile", "default"))
        assets_dir = (config_path.parent / overlays_cfg.get("image_asset_dir", "./input/assets/obrainrot/trump")).resolve()
        style_events: list[dict] | None = None
        if gemini_project_dir:
            script_payload = load_json_generic(gemini_project_dir / "script-lines.json")
            annotations_payload = load_json_generic(gemini_project_dir / "edit-annotations.json")
            complex_payload = build_complex_overlay_payload(
                manifest_payload=manifest_payload,
                script_payload=script_payload,
                annotations_payload=annotations_payload,
                image_asset_dir=assets_dir,
                video_width=int(config.get("timeline", {}).get("width", 1920)),
                video_height=int(config.get("timeline", {}).get("height", 1080)),
                safe_margin=int(overlays_cfg.get("safe_margin", 64)),
                overlay_width=int(overlays_cfg.get("overlay_width", 512)),
                overlay_height=int(overlays_cfg.get("overlay_height", 512)),
                anchor=str(overlays_cfg.get("anchor", "bottom_left")),
                checkpoint_cycle=[
                    str((config_path.parent / str(x)).resolve())
                    for x in overlays_cfg.get("dialogue", {}).get("checkpoint_cycle", [])
                ],
                style_rules=list(overlays_cfg.get("style_theme_rules", [])),
            )
            subtitle_segments = list(complex_payload["subtitle_segments"])
            image_events = list(complex_payload["image_overlays"])
            style_events = list(complex_payload.get("style_events", []))
            overlay_manifest_path = (output_dir / "overlay_manifest.json").resolve()
            write_json(overlay_manifest_path, validate_overlay_manifest(complex_payload))
            write_json_generic(output_dir / "dialogue_plan.json", {"dialogue_plan": complex_payload.get("dialogue_plan", [])})
        else:
            subtitle_segments = build_subtitle_segments_from_manifest(manifest_payload)
            image_events = build_image_events(
                subtitle_segments=subtitle_segments,
                asset_dir=assets_dir,
                video_width=int(config.get("timeline", {}).get("width", 1920)),
                video_height=int(config.get("timeline", {}).get("height", 1080)),
                safe_margin=int(overlays_cfg.get("safe_margin", 64)),
                overlay_width=int(overlays_cfg.get("overlay_width", 512)),
                overlay_height=int(overlays_cfg.get("overlay_height", 512)),
                anchor=str(overlays_cfg.get("anchor", "bottom_left")),
                keyword_map=overlays_cfg.get("keyword_map", {}),
            )
            overlay_manifest_path = (output_dir / "overlay_manifest.json").resolve()
            write_json(
                overlay_manifest_path,
                validate_overlay_manifest(
                    {
                        "style": STYLE_PRESETS.get(profile_name, STYLE_PRESETS["default"]),
                        "subtitle_segments": subtitle_segments,
                        "image_overlays": image_events,
                    }
                ),
            )
            style_events = None

        subtitle_outputs = write_subtitles(
            subtitle_segments=subtitle_segments,
            output_dir=output_dir,
            profile_name=profile_name if profile_name in STYLE_PRESETS else "default",
            max_chars_per_line=int(overlays_cfg.get("max_chars_per_line", 36)),
            max_lines_per_cue=int(overlays_cfg.get("max_lines_per_cue", 2)),
            style_events=style_events,
        )
        overlay_subtitles_ass = Path(subtitle_outputs["ass"])
        image_events_path = (output_dir / "image_events.json").resolve()
        write_json(image_events_path, {"image_overlays": image_events})
        fusion_template = (config_path.parent / "templates/textplus_subtitle_template.setting").resolve()
        fusion_out_dir = (output_dir / "fusion_settings").resolve()
        fusion_manifest = build_fusion_settings(
            overlay_manifest_path=overlay_manifest_path,
            template_path=fusion_template,
            output_dir=fusion_out_dir,
            center_x=float(overlays_cfg.get("fusion_center_x", 0.5)),
            center_y=float(overlays_cfg.get("fusion_center_y", 0.15)),
        )
        print(f"Overlay manifest: {overlay_manifest_path}")
        print(f"Fusion .setting manifest: {fusion_manifest}")

    
    variant_manifest_paths: dict[str, Path] = {}
    dialogue_audio_path: Path | None = None
    if args.generate_dialogue_audio:
        if not overlay_manifest_path:
            raise RuntimeError("--generate-dialogue-audio requires overlays to be enabled")
        print("Step F: generate multi-character dialogue audio")
        overlays_cfg = config.get("overlays", {})
        dialogue_out = (config_path.parent / overlays_cfg.get("dialogue", {}).get("output_wav", "./output/overlays/dialogue_mix.wav")).resolve()
        dialogue_work = (config_path.parent / overlays_cfg.get("dialogue", {}).get("work_dir", "./output/overlays/dialogue_turns")).resolve()
        dialogue_json = overlay_manifest_path.parent / "dialogue_plan.json"
        if not dialogue_json.exists():
            manifest_payload = load_json_generic(overlay_manifest_path)
            write_json_generic(dialogue_json, {"dialogue_plan": manifest_payload.get("dialogue_plan", [])})
        synth_script = (config_path.parent.parent / "voice_tts/scripts/synthesize_dialogue_csm.py").resolve()
        run_cmd(
            [
                "python3",
                str(synth_script),
                "--dialogue-json",
                str(dialogue_json),
                "--out",
                str(dialogue_out),
                "--work-dir",
                str(dialogue_work),
                "--model-name",
                str(overlays_cfg.get("dialogue", {}).get("model_name", "unsloth/csm-1b")),
                "--sentence-only",
                "--prefer-nltk",
                "--max-new-tokens",
                str(int(overlays_cfg.get("dialogue", {}).get("fast_max_new_tokens", 96))),
            ]
        )
        dialogue_audio_path = dialogue_out
        print(f"Dialogue audio: {dialogue_out}")

    if args.prebake_overlays:
        if not overlay_manifest_path:
            raise RuntimeError("--prebake-overlays requires --with-overlays")
        print("Step G: prebake overlays into normalized clips")
        prebake_dir = (config_path.parent / config.get("overlays", {}).get("paths", {}).get("prebake_dir", "./output/prebaked")).resolve()
        for variant in variant_names:
            variant_out_dir = prebake_dir / variant
            variant_manifest_paths[variant] = prebake_manifest(
                manifest_path=effective_manifest,
                overlay_manifest_path=overlay_manifest_path,
                output_dir=variant_out_dir,
                orientation=variant,
                font_color=str(config.get("overlays", {}).get("text", {}).get("font_color", "white")),
                box_color=str(config.get("overlays", {}).get("text", {}).get("box_color", "black@0.45")),
            )
            print(f"Prebaked manifest ({variant}): {variant_manifest_paths[variant]}")
    variant_outputs = build_timeline_variants(
        config_path=config_path,
        manifest_path=effective_manifest,
        base_output_path=timeline_output,
        overlay_manifest_path=overlay_manifest_path,
        variants=variant_names,
        variant_manifest_paths=variant_manifest_paths if variant_manifest_paths else None,
        dialogue_audio_path=dialogue_audio_path,
    )
    if not variant_outputs:
        build_timeline(
            config_path,
            effective_manifest,
            timeline_output,
            overlay_manifest_path=overlay_manifest_path,
            dialogue_audio_path=dialogue_audio_path,
        )
        variant_outputs = [timeline_output]

    if args.with_preview:
        print("Step E: compose FFmpeg preview")
        if not overlay_subtitles_ass or not image_events_path:
            raise RuntimeError("--with-preview requires overlay artifacts; use --with-overlays")
        preview_path = (config_path.parent / config.get("overlays", {}).get("paths", {}).get("preview_output", "./output/overlays/preview_overlay.mp4")).resolve()
        manifest_payload = load_config(effective_manifest)
        first_entry = manifest_payload.get("entries", [])[0]
        video_source = Path(first_entry["review"] or first_entry["normalized"]).resolve()
        compose_preview(video_path=video_source, ass_path=overlay_subtitles_ass, image_events_path=image_events_path, output_path=preview_path)
        print(f"Overlay preview: {preview_path}")

    print("\nPipeline complete.")
    print(f"- Manifest: {effective_manifest}")
    for out in variant_outputs:
        print(f"- Timeline: {out}")
    if overlay_manifest_path:
        print(f"- Overlay manifest: {overlay_manifest_path}")
    print("\nNext manual step in DaVinci Resolve:")
    print("1) Import normalized media first")
    print("2) Import generated FCPXML timeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
