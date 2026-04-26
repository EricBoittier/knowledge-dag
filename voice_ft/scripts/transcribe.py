#!/usr/bin/env python3
"""Run ASR with a base Whisper model + optional LoRA adapter (Unsloth)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import torch
from peft import PeftModel
from transformers import pipeline

from common import WHISPER_MODEL_ID, load_model_and_tokenizer
from unsloth import FastModel


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path, help="Path to audio file")
    p.add_argument(
        "--base-model",
        default=WHISPER_MODEL_ID,
        help="Base Whisper checkpoint (must match training base)",
    )
    p.add_argument(
        "--lora-dir",
        type=Path,
        default=None,
        help="Directory with LoRA weights from train.py --save-lora",
    )
    p.add_argument("--load-in-4bit", action="store_true")
    p.add_argument(
        "--dtype",
        choices=("float16", "bfloat16", "float32"),
        default="float16",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if not args.audio.is_file():
        raise SystemExit(f"Audio not found: {args.audio}")

    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    torch_dtype = dtype_map[args.dtype]

    model, tokenizer = load_model_and_tokenizer(
        model_name=args.base_model,
        load_in_4bit=args.load_in_4bit,
    )
    if args.lora_dir is not None:
        if not args.lora_dir.is_dir():
            raise SystemExit(f"--lora-dir is not a directory: {args.lora_dir}")
        model = PeftModel.from_pretrained(model, str(args.lora_dir))

    FastModel.for_inference(model)
    model.eval()

    whisper = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=tokenizer.tokenizer,
        feature_extractor=tokenizer.feature_extractor,
        processor=tokenizer,
        return_language=True,
        torch_dtype=torch_dtype,
    )
    result = whisper(str(args.audio))
    print(result["text"])


if __name__ == "__main__":
    main()
