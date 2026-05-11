#!/usr/bin/env python3
"""
Per-frame Z-Image wrapper CLI for style_transfer_video.py.

This script accepts input/output frame paths and runs a Z-Image Diffusers pipeline.
It is intended to be called via style_transfer_video.py --z-image-cmd template.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stylize one frame using Z-Image via Diffusers.")
    parser.add_argument("--input", required=True, help="Input frame path")
    parser.add_argument("--output", required=True, help="Output frame path")
    parser.add_argument("--prompt", default="", help="Prompt text")
    parser.add_argument("--negative", default="", help="Negative prompt text")
    parser.add_argument("--style", default="", help="Optional style reference image path")
    parser.add_argument("--model-id", default="Tongyi-MAI/Z-Image-Turbo", help="Diffusers model id")
    parser.add_argument("--steps", type=int, default=8, help="Inference steps")
    parser.add_argument("--guidance-scale", type=float, default=0.0, help="Guidance scale")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="Execution device",
    )
    return parser.parse_args()


def pick_device(device_arg: str) -> str:
    import torch  # type: ignore

    if device_arg == "cpu":
        return "cpu"
    if device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("Requested --device cuda but CUDA is unavailable.")
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_pipeline(model_id: str, device: str):
    import torch  # type: ignore
    from diffusers import ZImagePipeline  # type: ignore

    torch_dtype = torch.bfloat16 if device == "cuda" else torch.float32
    pipe = ZImagePipeline.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
    )
    if device == "cuda":
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.to(device)
    return pipe


def stylize_frame(args: argparse.Namespace) -> None:
    import torch  # type: ignore
    from PIL import Image  # type: ignore

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input frame not found: {input_path}")

    device = pick_device(args.device)
    pipe = load_pipeline(args.model_id, device)
    generator = torch.Generator(device=device).manual_seed(args.seed)

    frame = Image.open(input_path).convert("RGB")
    style_image = None
    if args.style:
        style_path = Path(args.style).expanduser().resolve()
        if style_path.exists():
            style_image = Image.open(style_path).convert("RGB")
        else:
            print(f"Warning: style image not found, ignoring: {style_path}", file=sys.stderr)

    call_common = dict(
        prompt=args.prompt,
        negative_prompt=args.negative,
        num_inference_steps=max(1, int(args.steps)),
        guidance_scale=float(args.guidance_scale),
        generator=generator,
        width=frame.width,
        height=frame.height,
    )

    # Z-Image variants can differ by installed version; attempt compatible signatures.
    last_error: Exception | None = None
    outputs = None
    attempts = [
        {**call_common, "image": frame, "style_image": style_image},
        {**call_common, "image": frame},
        {**call_common, "style_image": style_image},
        {**call_common},
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

    if outputs is None:
        raise RuntimeError(f"No compatible Z-Image call signature worked: {last_error}")

    if not hasattr(outputs, "images") or not outputs.images:
        raise RuntimeError("Pipeline did not return images.")
    outputs.images[0].save(output_path)

    if device == "cuda":
        torch.cuda.empty_cache()


def main() -> int:
    args = parse_args()
    try:
        stylize_frame(args)
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
