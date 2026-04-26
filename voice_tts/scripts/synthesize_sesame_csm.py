#!/usr/bin/env python3
"""Synthesize speech with Sesame CSM-1B + optional LoRA (Unsloth).

Examples:
  python3 scripts/synthesize_sesame_csm.py --text "Hello world" --out out.wav
  python3 scripts/synthesize_sesame_csm.py --lora-dir ../sesame_csm_lora \\
    --text "Fine tuned voice." --out out.wav
  # Voice consistency: same speaker clip + transcript as context (24 kHz WAV):
  python3 scripts/synthesize_sesame_csm.py --lora-dir ../sesame_csm_lora \\
    --context-wav ref.wav --context-text "Exact words spoken in ref.wav" \\
    --text "New sentence to speak." --out out.wav
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

_ROOT = Path(__file__).resolve().parent.parent
_KD = _ROOT.parent
if str(_KD) not in sys.path:
    sys.path.insert(0, str(_KD))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import soundfile as sf
import torch
from unsloth import FastModel
from peft import PeftModel
from transformers import AutoProcessor, CsmForConditionalGeneration

from csm_model_patches import (
    patch_csm_create_causal_mask_for_1d_position_ids,
    patch_depth_decoder_causal_lm_forward,
    patch_depth_decoder_embedding_clone,
)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-name", default="unsloth/csm-1b")
    p.add_argument("--lora-dir", type=Path, default=None)
    p.add_argument("--text", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--speaker-id", type=int, default=0)
    p.add_argument("--max-new-tokens", type=int, default=250, help="~125 tok ≈ 10 s at 24 kHz")
    p.add_argument("--context-wav", type=Path, default=None)
    p.add_argument("--context-text", type=str, default=None)
    p.add_argument("--device", default=None, help="cuda or cpu (default: auto)")
    return p.parse_args()


def main():
    args = parse_args()
    patch_csm_create_causal_mask_for_1d_position_ids()
    if args.context_wav is not None and not args.context_wav.is_file():
        raise SystemExit(f"Missing --context-wav: {args.context_wav}")
    if args.context_wav is not None and not args.context_text:
        raise SystemExit("--context-text is required when using --context-wav")

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    model, _tokenizer_backend = FastModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=2048,
        dtype=None,
        auto_model=CsmForConditionalGeneration,
        load_in_4bit=False,
    )
    processor = AutoProcessor.from_pretrained(args.model_name)
    if args.lora_dir is not None:
        if not args.lora_dir.is_dir():
            raise SystemExit(f"--lora-dir is not a directory: {args.lora_dir}")
        model = PeftModel.from_pretrained(model, str(args.lora_dir))

    FastModel.for_inference(model)
    model.eval()
    model.to(device)

    # Unsloth replaces depth-decoder forward with (*args, **kwargs), so Transformers 5.5
    # generate() rejects backbone_last_hidden_state in model_kwargs. Training patches restore
    # HF-forward behavior and the embedding clone (in-place row-0 write + PEFT).
    patch_depth_decoder_embedding_clone(model)
    patch_depth_decoder_causal_lm_forward(model)

    sid = str(args.speaker_id)

    if args.context_wav is not None:
        ctx_audio, sr = sf.read(str(args.context_wav), dtype="float32", always_2d=False)
        if sr != 24_000:
            raise SystemExit(f"Context WAV must be 24 kHz, got {sr}")
        if ctx_audio.ndim > 1:
            ctx_audio = ctx_audio.mean(axis=1)
        conversation = [
            {
                "role": sid,
                "content": [
                    {"type": "text", "text": args.context_text},
                    {"type": "audio", "path": np.asarray(ctx_audio, dtype=np.float32)},
                ],
            },
            {"role": sid, "content": [{"type": "text", "text": args.text}]},
        ]
        inputs = processor.apply_chat_template(
            conversation,
            tokenize=True,
            return_dict=True,
        )
    else:
        conversation = [
            {"role": sid, "content": [{"type": "text", "text": args.text}]},
        ]
        inputs = processor.apply_chat_template(
            conversation,
            tokenize=True,
            return_dict=True,
        )

    inputs = inputs.to(device)
    with torch.no_grad():
        audio_values = model.generate(
            **inputs,
            max_new_tokens=args.max_new_tokens,
            output_audio=True,
        )
    audio = audio_values[0].to(torch.float32).cpu().numpy()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(args.out), audio, 24_000)
    print(args.out.resolve())


if __name__ == "__main__":
    main()
