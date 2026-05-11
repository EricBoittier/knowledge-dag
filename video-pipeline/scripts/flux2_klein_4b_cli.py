#!/usr/bin/env python3
"""
Text-to-image and image-conditioned generation for FLUX.2 [klein] 4B (Diffusers).

Pass one or more ``--image`` paths for editing / multi-reference conditioning (the
pipeline accepts a list of PIL images). Describe references in the prompt the way
the model expects (e.g. anchors like "image 1", "image 2" in multi-reference examples).

Default model: black-forest-labs/FLUX.2-klein-4B (distilled; Apache 2.0).

Install (Flux2 support may require a recent diffusers; upgrade if import fails):

  pip install -U torch torchvision accelerate
  pip install -U diffusers transformers sentencepiece protobuf

If Flux2KleinPipeline is missing, try the development branch per the model card:

  pip install git+https://github.com/huggingface/diffusers.git

First run downloads weights from Hugging Face (~tens of GB). Ensure HF_TOKEN is set
if a mirror or private fork requires it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate one image with FLUX.2 Klein 4B (Diffusers).",
    )
    p.add_argument(
        "--prompt",
        required=True,
        help="Text prompt (required; for multi-reference, mention images in the prompt as in BFL examples)",
    )
    p.add_argument(
        "--output",
        default="flux2_klein_out.png",
        help="Output image path (.png recommended)",
    )
    p.add_argument(
        "--image",
        action="append",
        default=None,
        metavar="PATH",
        help="Reference or source image; repeat for multiple references (I2I / editing)",
    )
    p.add_argument(
        "--model-id",
        default="black-forest-labs/FLUX.2-klein-4B",
        help="Diffusers model repo id",
    )
    p.add_argument(
        "--width",
        type=int,
        default=None,
        help="Output width in pixels (default: 1024 for text-only; with --image, inferred from images unless set)",
    )
    p.add_argument(
        "--height",
        type=int,
        default=None,
        help="Output height in pixels (default: 1024 for text-only; with --image, inferred unless set)",
    )
    p.add_argument(
        "--steps",
        type=int,
        default=4,
        help="Inference steps (4 is typical for this distilled checkpoint)",
    )
    p.add_argument(
        "--guidance-scale",
        type=float,
        default=1.0,
        help="Guidance scale (BFL recommends 1.0 for this 4B distilled model)",
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="Device for the generator and pipeline",
    )
    p.add_argument(
        "--memory",
        default="model",
        choices=("none", "model", "sequential"),
        help="CUDA memory strategy: none=all GPU; model=enable_model_cpu_offload; "
        "sequential=enable_sequential_cpu_offload (slowest, lowest VRAM)",
    )
    return p.parse_args()


def pick_device(device_arg: str) -> str:
    import torch

    if device_arg == "cpu":
        return "cpu"
    if device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("Requested --device cuda but CUDA is unavailable.")
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_pipeline(model_id: str, device: str, memory: str):
    import torch

    try:
        from diffusers import Flux2KleinPipeline
    except ImportError as ex:
        raise ImportError(
            "Flux2KleinPipeline not found. Upgrade diffusers, e.g. "
            "`pip install -U diffusers` or "
            "`pip install git+https://github.com/huggingface/diffusers.git`"
        ) from ex

    torch_dtype = torch.bfloat16 if device == "cuda" else torch.float32
    pipe = Flux2KleinPipeline.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
    )
    if device == "cuda":
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        if memory == "sequential":
            pipe.enable_sequential_cpu_offload()
        elif memory == "model":
            pipe.enable_model_cpu_offload()
        else:
            pipe.to("cuda")
    else:
        pipe.to("cpu")
    return pipe


def run(args: argparse.Namespace) -> None:
    import torch
    from PIL import Image

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    condition_paths: list[Path] = []
    if args.image:
        for raw in args.image:
            ip = Path(raw).expanduser().resolve()
            if not ip.is_file():
                raise FileNotFoundError(f"Image not found: {ip}")
            condition_paths.append(ip)

    device = pick_device(args.device)
    if device == "cpu" and args.memory != "none":
        print("Note: --memory offload options apply to CUDA only; using CPU.", file=sys.stderr)

    pipe = load_pipeline(args.model_id, device, args.memory if device == "cuda" else "none")
    gen_device = device
    generator = torch.Generator(device=gen_device).manual_seed(int(args.seed))

    call_kw: dict = dict(
        prompt=args.prompt,
        guidance_scale=float(args.guidance_scale),
        num_inference_steps=max(1, int(args.steps)),
        generator=generator,
    )

    if condition_paths:
        pil_images = [Image.open(p).convert("RGB") for p in condition_paths]
        call_kw["image"] = pil_images[0] if len(pil_images) == 1 else pil_images
        if args.width is not None:
            call_kw["width"] = int(args.width)
        if args.height is not None:
            call_kw["height"] = int(args.height)
        if len(pil_images) > 1:
            print(
                "Multi-reference: use a prompt that refers to each image (see BFL / Comfy Klein examples).",
                file=sys.stderr,
            )
    else:
        w = int(args.width) if args.width is not None else 1024
        h = int(args.height) if args.height is not None else 1024
        call_kw["width"] = w
        call_kw["height"] = h

    result = pipe(**call_kw)
    if not hasattr(result, "images") or not result.images:
        raise RuntimeError("Pipeline returned no images.")
    result.images[0].save(out)
    print(str(out))

    if device == "cuda":
        torch.cuda.empty_cache()


def main() -> int:
    args = parse_args()
    try:
        run(args)
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
