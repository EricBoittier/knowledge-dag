#!/usr/bin/env python3
"""
Offline video style transfer using FFmpeg plus an image model.

By default this uses in-process Hugging Face Diffusers with FLUX.2-klein-4B
(``--stylize-engine flux2_klein``). Alternatively, pass ``--z-image-cmd`` to run a
custom per-frame shell command, or ``--stylize-engine zimage`` for Z-Image Turbo.

This script:
1) extracts video frames
2) runs stylization (batch Diffusers or subprocess template)
3) re-encodes stylized frames back into a video and remuxes original audio
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], *, quiet: bool = False) -> None:
    if quiet:
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(shlex.quote(part) for part in cmd)}\n{completed.stderr}"
            )
        return
    print("+", " ".join(shlex.quote(part) for part in cmd))
    subprocess.run(cmd, check=True)


# Second-pass cleanup after minterpolate / keyframe blends: temporal denoise + light smoothing.
POST_CLEAN_VF_DEFAULT = "hqdn3d=2:1:3:2,atadenoise=s=15"

# Match video-pipeline/README.md + normalize_clips.py (DaVinci-friendly mezzanine).
_DEFAULT_MEDIA_POLICY: dict[str, str | int] = {
    "video_codec": "dnxhd",
    "video_profile": "dnxhr_hq",
    "pixel_format": "yuv422p",
    "audio_codec": "pcm_s16le",
    "audio_sample_rate": 48000,
    "audio_channels": 2,
}


def default_project_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "project_config.json"


def load_davinci_media_policy(config_path: Path | None) -> dict[str, str | int]:
    policy = dict(_DEFAULT_MEDIA_POLICY)
    path = config_path or default_project_config_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            mp = raw.get("media_policy") or {}
            for key in (
                "video_codec",
                "video_profile",
                "pixel_format",
                "audio_codec",
                "audio_sample_rate",
                "audio_channels",
            ):
                if key in mp and mp[key] is not None:
                    policy[key] = mp[key]  # type: ignore[assignment]
        except (OSError, json.JSONDecodeError):
            pass
    return policy


def probe_has_audio_stream(path: Path) -> bool:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(completed.stdout.strip())


def transcode_to_davinci_mezzanine_mov(
    src: Path,
    dst: Path,
    *,
    policy: dict[str, str | int],
    output_fps: float | str,
    ffmpeg_overwrite_flag: str,
    quiet: bool,
) -> None:
    """H.264 (or any) → QuickTime MOV with DNxHR HQ + PCM, per repo media_policy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".mezz.tmp" + dst.suffix)
    if tmp.exists():
        tmp.unlink()
    has_audio = probe_has_audio_stream(src)
    cmd: list[str] = [
        "ffmpeg",
        ffmpeg_overwrite_flag,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-c:v",
        str(policy["video_codec"]),
        "-profile:v",
        str(policy["video_profile"]),
        "-pix_fmt",
        str(policy["pixel_format"]),
        "-r",
        str(output_fps),
    ]
    if has_audio:
        cmd += [
            "-map",
            "0:a:0",
            "-c:a",
            str(policy["audio_codec"]),
            "-ar",
            str(policy["audio_sample_rate"]),
            "-ac",
            str(policy["audio_channels"]),
        ]
    else:
        cmd.append("-an")
    cmd.append(str(tmp))
    run(cmd, quiet=quiet)
    dst.unlink(missing_ok=True)
    tmp.replace(dst)


def transcode_mp4_to_mezzanine_mov_sibling(
    mp4_path: Path,
    *,
    policy: dict[str, str | int],
    output_fps: float | str,
    ffmpeg_overwrite_flag: str,
    quiet: bool,
) -> None:
    mov_path = mp4_path.with_suffix(".mov")
    transcode_to_davinci_mezzanine_mov(
        mp4_path,
        mov_path,
        policy=policy,
        output_fps=output_fps,
        ffmpeg_overwrite_flag=ffmpeg_overwrite_flag,
        quiet=quiet,
    )


def apply_post_clean_pass(
    output_video: Path,
    work_dir: Path,
    *,
    vf: str,
    video_codec: str,
    crf: int,
    pix_fmt: str,
    ffmpeg_overwrite_flag: str,
    quiet: bool,
) -> None:
    tmp_out = work_dir / f"{output_video.stem}.postclean.tmp{output_video.suffix}"
    if tmp_out.exists():
        tmp_out.unlink()
    run(
        [
            "ffmpeg",
            ffmpeg_overwrite_flag,
            "-i",
            str(output_video),
            "-vf",
            vf,
            "-c:v",
            video_codec,
            "-crf",
            str(crf),
            "-pix_fmt",
            pix_fmt,
            "-c:a",
            "copy",
            str(tmp_out),
        ],
        quiet=quiet,
    )
    output_video.unlink(missing_ok=True)
    tmp_out.replace(output_video)


def get_duration_seconds(video_path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return float(completed.stdout.strip())


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(video_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    raw = completed.stdout.strip()
    try:
        width_str, height_str = raw.split("x", 1)
        return int(width_str), int(height_str)
    except Exception as ex:
        raise RuntimeError(f"Unable to parse video dimensions for {video_path}: {raw}") from ex


def detect_scene_cuts(
    video_path: Path,
    scene_threshold: float,
    cuts_file: Path,
    quiet: bool,
) -> list[float]:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-filter:v",
            f"select='gt(scene,{scene_threshold})',metadata=print:file={cuts_file}",
            "-an",
            "-f",
            "null",
            "-",
        ],
        quiet=quiet,
    )
    if not cuts_file.exists():
        return []

    cuts: list[float] = []
    for line in cuts_file.read_text(encoding="utf-8").splitlines():
        if "pts_time=" not in line:
            continue
        _, value = line.split("pts_time=", 1)
        try:
            cuts.append(float(value.strip()))
        except ValueError:
            continue
    return sorted(set(cuts))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply image style transfer model to a video via extracted frames."
    )
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--output", required=True, help="Output video path")
    parser.add_argument(
        "--work-dir",
        default="./output/style_transfer_work",
        help="Working directory for extracted/stylized frames",
    )
    parser.add_argument("--fps", type=float, default=12.0, help="Extraction/re-encode frame rate")
    parser.add_argument(
        "--stylize-scale",
        type=float,
        default=1.0,
        help=(
            "Scale factor for extracted/stylized frames (e.g. 0.5 for half-res). "
            "Final output can be upscaled back to input resolution."
        ),
    )
    parser.add_argument(
        "--upscale-to-input",
        action="store_true",
        help="Upscale stylized video back to original input resolution for final output.",
    )
    parser.add_argument(
        "--stylize-every-nth-frame",
        type=int,
        default=1,
        help=(
            "Stylize every Nth target frame by lowering stylization FPS to fps/N "
            "(default: 1, stylize all frames)"
        ),
    )
    parser.add_argument(
        "--interpolate-mode",
        choices=("none", "framerate", "minterpolate"),
        default="minterpolate",
        help=(
            "When stylize-every-nth-frame > 1, upsample back to target fps using "
            "none (frame duplication), framerate (blend), or minterpolate (motion-comp)"
        ),
    )
    parser.add_argument(
        "--scene-cut-aware",
        action="store_true",
        help="Apply interpolation per scene segment to avoid cross-cut artifacts",
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=0.3,
        help="FFmpeg scene threshold for --scene-cut-aware (default: 0.3)",
    )
    parser.add_argument("--image-ext", default="png", help="Frame image extension (default: png)")
    parser.add_argument(
        "--z-image-cmd",
        default="",
        help=(
            "Stylizer command template for subprocess mode. "
            "Required placeholders: {input}, {output}. "
            "Optional placeholders: {style}, {prompt}, {negative_prompt}. "
            "If empty, runs in-process batch stylization (see --stylize-engine)."
        ),
    )
    parser.add_argument(
        "--stylize-engine",
        choices=("flux2_klein", "zimage"),
        default="flux2_klein",
        help=(
            "In-process Diffusers backend when --z-image-cmd is not set "
            "(default: flux2_klein / FLUX.2-klein-4B)."
        ),
    )
    parser.add_argument(
        "--python-zimage-batch",
        action="store_true",
        help=(
            "Shortcut: same as --stylize-engine zimage (loads ZImagePipeline once). "
            "Overrides --stylize-engine."
        ),
    )
    parser.add_argument(
        "--flux-model-id",
        default="black-forest-labs/FLUX.2-klein-4B",
        help="Hugging Face model id when --stylize-engine flux2_klein",
    )
    parser.add_argument(
        "--flux-steps",
        type=int,
        default=4,
        help="Inference steps for FLUX.2 Klein distilled (flux2_klein engine)",
    )
    parser.add_argument(
        "--flux-guidance-scale",
        type=float,
        default=1.0,
        help="Guidance scale for flux2_klein (ignored for step-distilled Klein)",
    )
    parser.add_argument(
        "--zimage-model-id",
        default="Tongyi-MAI/Z-Image-Turbo",
        help="Model id when --stylize-engine zimage (or --python-zimage-batch)",
    )
    parser.add_argument(
        "--zimage-steps",
        type=int,
        default=2,
        help="Inference steps for zimage engine",
    )
    parser.add_argument(
        "--zimage-guidance-scale",
        type=float,
        default=0.0,
        help="Guidance scale for zimage engine",
    )
    parser.add_argument(
        "--zimage-seed",
        type=int,
        default=42,
        help="RNG seed for in-process batch stylization",
    )
    parser.add_argument(
        "--zimage-device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Execution device for in-process batch stylization (all engines)",
    )
    parser.add_argument(
        "--temporal-conditioning",
        action="store_true",
        help=(
            "For python batch mode, condition each frame on the previous stylized frame "
            "to improve temporal consistency."
        ),
    )
    parser.add_argument(
        "--temporal-blend",
        type=float,
        default=0.15,
        help=(
            "For python batch mode, blend current output with previous stylized frame "
            "(0 disables blend, 1 keeps only previous frame)."
        ),
    )
    parser.add_argument(
        "--reference-blend",
        type=float,
        default=0.7,
        help=(
            "When temporal conditioning is enabled and style image exists, "
            "blend weight of previous stylized frame against reference style image "
            "for style conditioning (0=reference only, 1=previous only)."
        ),
    )
    parser.add_argument(
        "--prev-frame-input-blend",
        type=float,
        default=0.25,
        help=(
            "Blend previous stylized frame into current input frame before generation "
            "to improve temporal consistency (0 disables, 1 previous-only)."
        ),
    )
    parser.add_argument(
        "--optical-flow-warp",
        action="store_true",
        help=(
            "Warp previous stylized frame with Farneback optical flow from source frames "
            "(requires opencv-python; single-frame / pack-grid=off only)."
        ),
    )
    parser.add_argument(
        "--flow-pyr-scale",
        type=float,
        default=0.5,
        help="Farneback pyramid scale for --optical-flow-warp",
    )
    parser.add_argument(
        "--flow-levels",
        type=int,
        default=3,
        help="Farneback pyramid levels for --optical-flow-warp",
    )
    parser.add_argument(
        "--flow-winsize",
        type=int,
        default=15,
        help="Farneback window size for --optical-flow-warp",
    )
    parser.add_argument(
        "--pack-grid",
        choices=("off", "2x2"),
        default="off",
        help=(
            "For python batch mode, pack multiple frames into one image before generation "
            "to improve throughput."
        ),
    )
    parser.add_argument(
        "--pack-padding",
        type=int,
        default=16,
        help="Padding around packed frame tiles (pixels).",
    )
    parser.add_argument(
        "--keyframe-interval",
        type=int,
        default=1,
        help=(
            "Stylize every Nth extracted frame and reuse previous stylized frame for "
            "intermediate frames (default: 1 = stylize all extracted frames)."
        ),
    )
    parser.add_argument(
        "--keyframe-scene-cuts",
        action="store_true",
        help="Force stylization on extracted frames nearest to scene cuts.",
    )
    parser.add_argument(
        "--keyframe-scene-threshold",
        type=float,
        default=0.3,
        help="FFmpeg scene threshold used by --keyframe-scene-cuts (default: 0.3).",
    )
    parser.add_argument("--style-image", default="", help="Optional style reference image path")
    parser.add_argument("--prompt", default="", help="Optional prompt for the stylizer")
    parser.add_argument("--negative-prompt", default="", help="Optional negative prompt")
    parser.add_argument(
        "--video-codec",
        default="libx264",
        help="Video codec for final encode (default: libx264)",
    )
    parser.add_argument(
        "--pix-fmt",
        default="yuv420p",
        help="Pixel format for final encode (default: yuv420p)",
    )
    parser.add_argument(
        "--crf", type=int, default=18, help="CRF for final encode when codec supports it"
    )
    parser.add_argument(
        "--post-clean-pass",
        action="store_true",
        help=(
            "Run a second FFmpeg pass on the final output to reduce interpolation flicker / "
            "ghosting (temporal denoise + light smoothing)."
        ),
    )
    parser.add_argument(
        "--post-clean-vf",
        default="",
        help="Custom video filter for --post-clean-pass (default: built-in hqdn3d+atadenoise chain).",
    )
    parser.add_argument(
        "--post-clean-crf",
        type=int,
        default=-1,
        help="CRF for post pass (default: same as --crf).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output/work files if they already exist",
    )
    parser.add_argument("--quiet", action="store_true", help="Reduce command output")
    return parser


def format_user_command(
    template: str,
    *,
    input_path: Path,
    output_path: Path,
    style_path: str,
    prompt: str,
    negative_prompt: str,
) -> list[str]:
    raw = template.format(
        input=str(input_path),
        output=str(output_path),
        style=style_path,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )
    return shlex.split(raw)


def _warp_rgb_with_farneback_flow(
    prev_rgb,
    *,
    prev_gray,
    curr_gray,
    pyr_scale: float,
    levels: int,
    winsize: int,
):
    """Warp prev_rgb toward curr geometry using prev->curr dense flow (backward sample)."""
    import cv2  # type: ignore
    import numpy as np

    if prev_gray.shape != curr_gray.shape:
        raise ValueError("Optical flow: grayscale shape mismatch between frames.")
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray,
        curr_gray,
        None,
        float(pyr_scale),
        int(levels),
        int(winsize),
        3,
        5,
        1.2,
        0,
    )
    h, w = prev_gray.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(w, dtype=np.float32),
        np.arange(h, dtype=np.float32),
    )
    map_x = grid_x - flow[:, :, 0]
    map_y = grid_y - flow[:, :, 1]
    arr = np.asarray(prev_rgb.convert("RGB"), dtype=np.uint8)
    warped = cv2.remap(
        arr,
        map_x,
        map_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    from PIL import Image as PILImage  # type: ignore

    return PILImage.fromarray(warped)


def interpolate_missing_keyframes(
    *,
    frames: list[Path],
    styled_dir: Path,
    keyframe_indices: set[int] | None,
    quiet: bool,
) -> None:
    if not keyframe_indices:
        return
    if len(keyframe_indices) < 2:
        return

    try:
        from PIL import Image  # type: ignore
    except Exception as ex:
        raise RuntimeError("Pillow is required for keyframe interpolation.") from ex

    keys = sorted(idx for idx in keyframe_indices if 0 <= idx < len(frames))
    if len(keys) < 2:
        return

    for a, b in zip(keys, keys[1:], strict=False):
        if b <= a + 1:
            continue
        start_path = styled_dir / frames[a].name
        end_path = styled_dir / frames[b].name
        if not start_path.exists() or not end_path.exists():
            continue
        start_img = Image.open(start_path).convert("RGB")
        end_img = Image.open(end_path).convert("RGB")
        if end_img.size != start_img.size:
            end_img = end_img.resize(start_img.size, Image.Resampling.LANCZOS)
        for idx in range(a + 1, b):
            alpha = (idx - a) / float(b - a)
            out = Image.blend(start_img, end_img, alpha=alpha)
            out.save(styled_dir / frames[idx].name)

    # After the last keyframe we cannot interpolate forward, so hold last style.
    last_key = keys[-1]
    last_path = styled_dir / frames[last_key].name
    if last_path.exists() and last_key < len(frames) - 1:
        last_img = Image.open(last_path).convert("RGB")
        for idx in range(last_key + 1, len(frames)):
            out_path = styled_dir / frames[idx].name
            if out_path.exists():
                continue
            last_img.save(out_path)
    if not quiet:
        print("Keyframe interpolation complete.")


def stylize_frames_python_batch(
    *,
    frames: list[Path],
    styled_dir: Path,
    engine: str,
    model_id: str,
    prompt: str,
    negative_prompt: str,
    style_image: str,
    steps: int,
    guidance_scale: float,
    seed: int,
    device_arg: str,
    temporal_conditioning: bool,
    temporal_blend: float,
    reference_blend: float,
    prev_frame_input_blend: float,
    optical_flow_warp: bool,
    flow_pyr_scale: float,
    flow_levels: int,
    flow_winsize: int,
    pack_grid: str,
    pack_padding: int,
    keyframe_indices: set[int] | None,
    quiet: bool,
) -> None:
    try:
        import torch  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as ex:
        raise RuntimeError(
            "Python batch stylizer dependencies missing. "
            "Install torch, pillow, and diffusers."
        ) from ex

    if engine == "zimage":
        try:
            from diffusers import ZImagePipeline  # type: ignore
        except Exception as ex:
            raise RuntimeError(
                "Z-Image batch mode requires diffusers with ZImagePipeline. "
                "Install: pip install -U diffusers"
            ) from ex
    elif engine == "flux2_klein":
        try:
            from diffusers import Flux2KleinPipeline  # type: ignore
        except Exception as ex:
            raise RuntimeError(
                "FLUX.2 Klein batch mode requires a recent diffusers with Flux2KleinPipeline. "
                "Try: pip install -U diffusers"
            ) from ex
    else:
        raise ValueError(f"Unknown stylize engine: {engine!r}")

    if device_arg == "cpu":
        device = "cpu"
    elif device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("Requested --zimage-device cuda but CUDA is unavailable.")
        device = "cuda"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    if device == "cuda":
        torch_dtype = torch.bfloat16
    else:
        torch_dtype = torch.float32

    if not quiet:
        print(f"Loading {engine} pipeline: {model_id} on {device}")
    if engine == "zimage":
        pipe = ZImagePipeline.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
    else:
        pipe = Flux2KleinPipeline.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
    if device == "cuda":
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.to(device)

    generator = torch.Generator(device=device).manual_seed(seed)

    style_ref = None
    if style_image:
        style_path = Path(style_image).expanduser().resolve()
        if style_path.exists():
            style_ref = Image.open(style_path).convert("RGB")
        elif not quiet:
            print(f"Warning: style image not found, ignoring: {style_path}", file=sys.stderr)

    def _pack_frames_2x2(images: list) -> tuple:
        from PIL import ImageOps  # type: ignore

        pad = max(0, int(pack_padding))
        base_w = images[0].width
        base_h = images[0].height
        tile_w = base_w + 2 * pad
        tile_h = base_h + 2 * pad
        canvas_w = 2 * tile_w
        canvas_h = 2 * tile_h
        canvas = Image.new("RGB", (canvas_w, canvas_h), color=(0, 0, 0))
        bboxes = []
        for i in range(4):
            col = i % 2
            row = i // 2
            x0 = col * tile_w
            y0 = row * tile_h
            if i < len(images):
                tile = ImageOps.expand(images[i], border=pad, fill=0)
                canvas.paste(tile, (x0, y0))
            bboxes.append((x0 + pad, y0 + pad, x0 + pad + base_w, y0 + pad + base_h))
        return canvas, bboxes

    def _split_frames_2x2(packed_image, bboxes: list[tuple[int, int, int, int]], count: int) -> list:
        out = []
        for i in range(count):
            out.append(packed_image.crop(bboxes[i]).convert("RGB"))
        return out

    def _pad_to_multiple_of_16(image):
        from PIL import ImageOps  # type: ignore

        w, h = image.size
        target_w = ((w + 15) // 16) * 16
        target_h = ((h + 15) // 16) * 16
        pad_right = target_w - w
        pad_bottom = target_h - h
        if pad_right == 0 and pad_bottom == 0:
            return image, (0, 0, w, h)
        padded = ImageOps.expand(image, border=(0, 0, pad_right, pad_bottom), fill=0)
        return padded, (0, 0, w, h)

    total = len(frames)
    previous_stylized = None
    previous_source_gray = None
    temporal_blend = max(0.0, min(1.0, float(temporal_blend)))
    reference_blend = max(0.0, min(1.0, float(reference_blend)))
    prev_frame_input_blend = max(0.0, min(1.0, float(prev_frame_input_blend)))
    group_size = 4 if pack_grid == "2x2" else 1
    for group_start in range(0, total, group_size):
        group_frames = frames[group_start : group_start + group_size]
        if group_size == 1 and keyframe_indices is not None:
            if group_start not in keyframe_indices:
                continue
        if not quiet:
            last_idx = group_start + len(group_frames)
            print(
                f"[{group_start + 1}-{last_idx}/{total}] Stylizing "
                f"{group_frames[0].name}..{group_frames[-1].name} ({engine} batch, pack={pack_grid})"
            )
        source_images = [Image.open(frame).convert("RGB") for frame in group_frames]
        if pack_grid == "2x2":
            source, unpack_bboxes = _pack_frames_2x2(source_images)
        else:
            source = source_images[0]
            unpack_bboxes = []

        curr_gray = None
        prev_aligned = None
        if optical_flow_warp and pack_grid == "off" and source_images:
            import cv2  # type: ignore
            import numpy as np  # type: ignore

            curr_gray = cv2.cvtColor(
                np.asarray(source_images[0], dtype=np.uint8),
                cv2.COLOR_RGB2GRAY,
            )

        if (
            optical_flow_warp
            and pack_grid == "off"
            and previous_stylized is not None
            and previous_source_gray is not None
            and curr_gray is not None
        ):
            try:
                prev_aligned = _warp_rgb_with_farneback_flow(
                    previous_stylized,
                    prev_gray=previous_source_gray,
                    curr_gray=curr_gray,
                    pyr_scale=flow_pyr_scale,
                    levels=flow_levels,
                    winsize=flow_winsize,
                )
            except Exception as ex:
                if not quiet:
                    print(
                        f"Warning: optical flow warp failed, using unwarped previous frame: {ex}",
                        file=sys.stderr,
                    )

        prev_for_temporal = None
        if previous_stylized is not None:
            prev_for_temporal = prev_aligned if prev_aligned is not None else previous_stylized

        if prev_for_temporal is not None and prev_frame_input_blend > 0.0:
            prev_for_input = prev_for_temporal
            if prev_for_input.size != source.size:
                prev_for_input = prev_for_input.resize(source.size, Image.Resampling.LANCZOS)
            source = Image.blend(source, prev_for_input, alpha=prev_frame_input_blend)
        padded_source, crop_box = _pad_to_multiple_of_16(source)

        temporal_style_ref = None
        if temporal_conditioning and prev_for_temporal is not None:
            if style_ref is not None:
                # Mix global style guidance with short-term temporal guidance.
                prev_for_style = prev_for_temporal
                if prev_for_style.size != style_ref.size:
                    prev_for_style = prev_for_style.resize(style_ref.size, Image.Resampling.LANCZOS)
                temporal_style_ref = Image.blend(style_ref, prev_for_style, alpha=reference_blend)
            else:
                temporal_style_ref = prev_for_temporal

        outputs = None
        last_error: Exception | None = None

        if engine == "zimage":
            base_kwargs = dict(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=max(1, int(steps)),
                guidance_scale=float(guidance_scale),
                generator=generator,
                width=padded_source.width,
                height=padded_source.height,
            )
            attempts = [
                {**base_kwargs, "image": padded_source, "style_image": temporal_style_ref or style_ref},
                {**base_kwargs, "image": padded_source},
                {**base_kwargs, "style_image": temporal_style_ref or style_ref},
                {**base_kwargs},
            ]
            for kwargs in attempts:
                if kwargs.get("style_image") is None:
                    kwargs.pop("style_image", None)
                try:
                    outputs = pipe(**kwargs)
                    break
                except TypeError as ex:
                    last_error = ex
                    continue
        else:
            # FLUX Klein: pass a list of PIL images for multi-reference editing (Diffusers
            # `image=[...]`). Image 1 is the current (possibly temporally blended) frame;
            # image 2 is temporal_style_ref when --temporal-conditioning is on (blend of
            # --style-image and previous stylized per --reference-blend), else --style-image.
            style_for_ref = temporal_style_ref if temporal_style_ref is not None else style_ref
            if prompt.strip():
                flux_prompt = prompt
            elif style_for_ref is not None:
                flux_prompt = (
                    "Apply the visual style of the second image to the first image, "
                    "preserving composition and layout."
                )
            else:
                flux_prompt = "Stylize and enhance this frame with high visual quality."
            cond_images: list = [padded_source]
            if style_for_ref is not None:
                sr = style_for_ref
                if sr.size != padded_source.size:
                    sr = sr.resize(padded_source.size, Image.Resampling.LANCZOS)
                cond_images.append(sr)
            img_arg = cond_images[0] if len(cond_images) == 1 else cond_images
            try:
                outputs = pipe(
                    image=img_arg,
                    prompt=flux_prompt,
                    width=padded_source.width,
                    height=padded_source.height,
                    num_inference_steps=max(1, int(steps)),
                    guidance_scale=float(guidance_scale),
                    generator=generator,
                )
            except Exception as ex:
                last_error = ex

        if outputs is None or not getattr(outputs, "images", None):
            raise RuntimeError(
                f"{engine} frame generation failed for group starting {group_frames[0].name}: {last_error}"
            )
        stylized_packed = outputs.images[0].convert("RGB").crop(crop_box)
        if pack_grid == "2x2":
            stylized_images = _split_frames_2x2(stylized_packed, unpack_bboxes, len(group_frames))
        else:
            stylized_images = [stylized_packed]

        for frame, stylized in zip(group_frames, stylized_images, strict=True):
            out_frame = styled_dir / frame.name
            if prev_for_temporal is not None and temporal_blend > 0.0:
                blend_src = prev_for_temporal
                if blend_src.size != stylized.size:
                    blend_src = blend_src.resize(stylized.size, Image.Resampling.LANCZOS)
                stylized = Image.blend(stylized, blend_src, alpha=temporal_blend)
            stylized.save(out_frame)
            previous_stylized = stylized
        if optical_flow_warp and pack_grid == "off" and curr_gray is not None:
            previous_source_gray = curr_gray.copy()
        elif pack_grid == "2x2":
            previous_source_gray = None
        if device == "cuda":
            torch.cuda.empty_cache()


def main() -> int:
    args = build_parser().parse_args()

    input_video = Path(args.input).expanduser().resolve()
    output_video = Path(args.output).expanduser().resolve()
    work_dir = Path(args.work_dir).expanduser().resolve()
    extracted_dir = work_dir / "frames"
    styled_dir = work_dir / "styled"

    if not input_video.exists():
        print(f"Error: input video not found: {input_video}", file=sys.stderr)
        return 1

    if args.stylize_every_nth_frame < 1:
        print("Error: --stylize-every-nth-frame must be >= 1", file=sys.stderr)
        return 1
    if args.stylize_scale <= 0:
        print("Error: --stylize-scale must be > 0", file=sys.stderr)
        return 1
    if args.keyframe_interval < 1:
        print("Error: --keyframe-interval must be >= 1", file=sys.stderr)
        return 1

    if output_video.exists() and not args.overwrite:
        print(
            f"Error: output already exists: {output_video} (use --overwrite to replace)",
            file=sys.stderr,
        )
        return 1

    work_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    styled_dir.mkdir(parents=True, exist_ok=True)
    output_video.parent.mkdir(parents=True, exist_ok=True)

    effective_fps = args.fps / args.stylize_every_nth_frame
    if effective_fps <= 0:
        print("Error: effective fps must be > 0", file=sys.stderr)
        return 1

    frame_pattern = f"%06d.{args.image_ext}"
    extracted_pattern = extracted_dir / frame_pattern
    styled_pattern = styled_dir / frame_pattern
    styled_base_video = work_dir / "styled_base.mp4"
    interpolated_input_video = styled_base_video

    ffmpeg_overwrite_flag = "-y" if args.overwrite else "-n"
    input_width, input_height = get_video_dimensions(input_video)

    extract_filter = f"fps={effective_fps}"
    if abs(args.stylize_scale - 1.0) > 1e-6:
        extract_filter = (
            f"{extract_filter},"
            f"scale='trunc(iw*{args.stylize_scale}/2)*2':'trunc(ih*{args.stylize_scale}/2)*2':flags=lanczos"
        )

    run(
        [
            "ffmpeg",
            ffmpeg_overwrite_flag,
            "-i",
            str(input_video),
            "-vf",
            extract_filter,
            str(extracted_pattern),
        ],
        quiet=args.quiet,
    )

    frames = sorted(extracted_dir.glob(f"*.{args.image_ext}"))
    if not frames:
        print("Error: no frames extracted", file=sys.stderr)
        return 1
    total = len(frames)

    keyframe_indices: set[int] | None = None
    if args.keyframe_interval > 1 or args.keyframe_scene_cuts:
        keyframe_indices = set(range(0, len(frames), args.keyframe_interval))
        keyframe_indices.add(0)
        if args.keyframe_scene_cuts:
            cuts_file = work_dir / "keyframe_scene_cuts.txt"
            cuts = detect_scene_cuts(
                video_path=input_video,
                scene_threshold=args.keyframe_scene_threshold,
                cuts_file=cuts_file,
                quiet=args.quiet,
            )
            for ts in cuts:
                idx = int(round(ts * effective_fps))
                idx = max(0, min(len(frames) - 1, idx))
                keyframe_indices.add(idx)
        if not args.quiet:
            print(
                f"Keyframe mode: stylizing {len(keyframe_indices)}/{len(frames)} extracted frames "
                f"(interval={args.keyframe_interval}, scene_cuts={args.keyframe_scene_cuts})"
            )

    use_subprocess_stylizer = bool(str(args.z_image_cmd).strip())

    if use_subprocess_stylizer:
        for idx, frame in enumerate(frames, start=1):
            out_frame = styled_dir / frame.name
            frame_index = idx - 1
            if keyframe_indices is not None and frame_index not in keyframe_indices:
                continue
            cmd = format_user_command(
                args.z_image_cmd,
                input_path=frame,
                output_path=out_frame,
                style_path=args.style_image,
                prompt=args.prompt,
                negative_prompt=args.negative_prompt,
            )
            if not args.quiet:
                print(f"[{idx}/{total}] Stylizing {frame.name}")
            run(cmd, quiet=args.quiet)
            if not out_frame.exists():
                print(
                    f"Error: stylizer did not produce expected output file: {out_frame}",
                    file=sys.stderr,
                )
                return 1
    else:
        batch_engine = "zimage" if args.python_zimage_batch else args.stylize_engine
        if batch_engine == "flux2_klein":
            b_model = args.flux_model_id
            b_steps = args.flux_steps
            b_guidance = args.flux_guidance_scale
        else:
            b_model = args.zimage_model_id
            b_steps = args.zimage_steps
            b_guidance = args.zimage_guidance_scale
        try:
            stylize_frames_python_batch(
                frames=frames,
                styled_dir=styled_dir,
                engine=batch_engine,
                model_id=b_model,
                prompt=args.prompt,
                negative_prompt=args.negative_prompt,
                style_image=args.style_image,
                steps=b_steps,
                guidance_scale=b_guidance,
                seed=args.zimage_seed,
                device_arg=args.zimage_device,
                temporal_conditioning=args.temporal_conditioning,
                temporal_blend=args.temporal_blend,
                reference_blend=args.reference_blend,
                prev_frame_input_blend=args.prev_frame_input_blend,
                optical_flow_warp=args.optical_flow_warp,
                flow_pyr_scale=args.flow_pyr_scale,
                flow_levels=args.flow_levels,
                flow_winsize=args.flow_winsize,
                pack_grid=args.pack_grid,
                pack_padding=args.pack_padding,
                keyframe_indices=keyframe_indices,
                quiet=args.quiet,
            )
        except Exception as ex:
            print(f"Error: batch stylizer failed: {ex}", file=sys.stderr)
            return 1

    interpolate_missing_keyframes(
        frames=frames,
        styled_dir=styled_dir,
        keyframe_indices=keyframe_indices,
        quiet=args.quiet,
    )

    for frame in frames:
        out_frame = styled_dir / frame.name
        if not out_frame.exists():
            print(
                f"Error: stylizer did not produce expected output file: {out_frame}",
                file=sys.stderr,
            )
            return 1

    # Build final video from stylized frames and source audio if present.
    if args.stylize_every_nth_frame == 1:
        final_scale_filter: str | None = None
        if args.upscale_to_input and abs(args.stylize_scale - 1.0) > 1e-6:
            final_scale_filter = f"scale={input_width}:{input_height}:flags=lanczos"
        run(
            [
                "ffmpeg",
                ffmpeg_overwrite_flag,
                "-framerate",
                str(args.fps),
                "-i",
                str(styled_pattern),
                "-i",
                str(input_video),
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                *([] if final_scale_filter is None else ["-vf", final_scale_filter]),
                "-c:v",
                args.video_codec,
                "-crf",
                str(args.crf),
                "-pix_fmt",
                args.pix_fmt,
                "-c:a",
                "aac",
                "-shortest",
                str(output_video),
            ],
            quiet=args.quiet,
        )
    else:
        final_scale_filter: str | None = None
        if args.upscale_to_input and abs(args.stylize_scale - 1.0) > 1e-6:
            final_scale_filter = f"scale={input_width}:{input_height}:flags=lanczos"
        run(
            [
                "ffmpeg",
                ffmpeg_overwrite_flag,
                "-framerate",
                str(effective_fps),
                "-i",
                str(styled_pattern),
                "-c:v",
                "libx264",
                "-crf",
                "12",
                "-pix_fmt",
                args.pix_fmt,
                str(styled_base_video),
            ],
            quiet=args.quiet,
        )

        if args.interpolate_mode == "none":
            interp_filter = f"fps={args.fps}"
        elif args.interpolate_mode == "framerate":
            interp_filter = f"framerate=fps={args.fps}"
        else:
            interp_filter = f"minterpolate=fps={args.fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"

        if args.scene_cut_aware and args.interpolate_mode != "none":
            cuts_file = work_dir / "scene_cuts.txt"
            segment_dir = work_dir / "scene_segments"
            segment_dir.mkdir(parents=True, exist_ok=True)

            cuts = detect_scene_cuts(
                video_path=styled_base_video,
                scene_threshold=args.scene_threshold,
                cuts_file=cuts_file,
                quiet=args.quiet,
            )
            duration = get_duration_seconds(styled_base_video)
            boundaries = [0.0] + [ts for ts in cuts if 0.0 < ts < duration] + [duration]
            boundaries = sorted(set(boundaries))
            if len(boundaries) > 2 and not args.quiet:
                print(f"Scene-cut-aware interpolation: {len(boundaries) - 1} segments")

            segment_paths: list[Path] = []
            for i in range(len(boundaries) - 1):
                start = boundaries[i]
                end = boundaries[i + 1]
                if end - start <= 0.01:
                    continue
                segment_path = segment_dir / f"segment_{i:04d}.mp4"
                run(
                    [
                        "ffmpeg",
                        ffmpeg_overwrite_flag,
                        "-ss",
                        f"{start:.6f}",
                        "-to",
                        f"{end:.6f}",
                        "-i",
                        str(styled_base_video),
                        "-vf",
                        interp_filter,
                        "-an",
                        "-c:v",
                        "libx264",
                        "-crf",
                        "12",
                        "-pix_fmt",
                        args.pix_fmt,
                        str(segment_path),
                    ],
                    quiet=args.quiet,
                )
                segment_paths.append(segment_path)

            if not segment_paths:
                print("Error: no scene segments generated for interpolation", file=sys.stderr)
                return 1

            concat_list = work_dir / "scene_concat.txt"
            concat_list.write_text(
                "".join(f"file '{segment.as_posix()}'\n" for segment in segment_paths),
                encoding="utf-8",
            )
            interpolated_input_video = work_dir / "styled_interpolated_sceneaware.mp4"
            run(
                [
                    "ffmpeg",
                    ffmpeg_overwrite_flag,
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_list),
                    "-c",
                    "copy",
                    str(interpolated_input_video),
                ],
                quiet=args.quiet,
            )
        else:
            interpolated_input_video = work_dir / "styled_interpolated.mp4"
            run(
                [
                    "ffmpeg",
                    ffmpeg_overwrite_flag,
                    "-i",
                    str(styled_base_video),
                    "-vf",
                    interp_filter,
                    "-an",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "12",
                    "-pix_fmt",
                    args.pix_fmt,
                    str(interpolated_input_video),
                ],
                quiet=args.quiet,
            )

        run(
            [
                "ffmpeg",
                ffmpeg_overwrite_flag,
                "-i",
                str(interpolated_input_video),
                "-i",
                str(input_video),
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                *([] if final_scale_filter is None else ["-vf", final_scale_filter]),
                "-c:v",
                args.video_codec,
                "-crf",
                str(args.crf),
                "-pix_fmt",
                args.pix_fmt,
                "-c:a",
                "aac",
                "-shortest",
                str(output_video),
            ],
            quiet=args.quiet,
        )

    if args.post_clean_pass:
        post_crf = args.post_clean_crf if args.post_clean_crf >= 0 else args.crf
        post_vf = args.post_clean_vf.strip() or POST_CLEAN_VF_DEFAULT
        if not args.quiet:
            print(f"Post-clean pass (second encode): vf={post_vf!r}")
        try:
            apply_post_clean_pass(
                output_video=output_video,
                work_dir=work_dir,
                vf=post_vf,
                video_codec=args.video_codec,
                crf=post_crf,
                pix_fmt=args.pix_fmt,
                ffmpeg_overwrite_flag=ffmpeg_overwrite_flag,
                quiet=args.quiet,
            )
        except Exception as ex:
            print(f"Error: post-clean pass failed: {ex}", file=sys.stderr)
            return 1

    skip_dnxhr = os.environ.get("STYLIZE_SKIP_DNXHR_MOV", "").lower() in (
        "1",
        "true",
        "yes",
    )
    cfg_raw = os.environ.get("DAVINCI_MEZZANINE_CONFIG", "").strip()
    mezz_cfg = Path(cfg_raw).expanduser().resolve() if cfg_raw else default_project_config_path()
    pol = load_davinci_media_policy(mezz_cfg if mezz_cfg.is_file() else None)

    if output_video.suffix.lower() == ".mov" and not skip_dnxhr:
        if not args.quiet:
            print(
                "Transcode to DaVinci mezzanine (DNxHR HQ + PCM s16le, per project_config media_policy)…"
            )
        transcode_to_davinci_mezzanine_mov(
            output_video,
            output_video,
            policy=pol,
            output_fps=args.fps,
            ffmpeg_overwrite_flag="-y",
            quiet=args.quiet,
        )

    if (
        output_video.suffix.lower() == ".mp4"
        and os.environ.get("STYLIZE_SKIP_MOV_SIBLING", "").lower()
        not in ("1", "true", "yes")
    ):
        mov_out = output_video.with_suffix(".mov")
        if not args.quiet:
            print(f"DaVinci mezzanine MOV sibling (DNxHR + PCM): {mov_out}")
        transcode_mp4_to_mezzanine_mov_sibling(
            output_video,
            policy=pol,
            output_fps=args.fps,
            ffmpeg_overwrite_flag=ffmpeg_overwrite_flag,
            quiet=args.quiet,
        )

    print(f"Done: {output_video}")
    print(
        "Frames stylized: "
        f"{total} at {effective_fps:.3f} fps (target {args.fps:.3f} fps), "
        f"work dir: {work_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
