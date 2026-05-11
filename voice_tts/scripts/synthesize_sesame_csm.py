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
from typing import Any

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
<<<<<<< HEAD
    patch_csm_create_causal_mask_for_1d_position_ids,
    patch_depth_decoder_causal_lm_forward,
    patch_depth_decoder_embedding_clone,
    sync_csm_backbone_audio_embedding_from_depth,
)


def _extract_generated_audio(out) -> torch.Tensor:
    """``model.generate(..., output_audio=True)`` may return a list of waveforms or a ``CsmGenerateOutput``."""
    if hasattr(out, "audio") and out.audio is not None:
        return out.audio[0]
    if isinstance(out, (list, tuple)) and len(out) > 0:
        return out[0]
    raise TypeError(
        f"Unexpected generate() return type {type(out)!r}; expected a list of audio tensors or CsmGenerateOutput "
        "with .audio set. Do not index with [0] on ModelOutput (that is token sequences, not waveform)."
    )


=======
    patch_depth_decoder_causal_lm_forward,
    patch_depth_decoder_embedding_clone,
)


>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)
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


def load_csm_for_inference(
    *,
    model_name: str,
    lora_dir: Path | None,
    device: str | None,
) -> tuple[Any, Any, str]:
    """Load CSM once for repeated ``synthesize_csm_to_file`` calls. Returns ``(model, processor, device)``."""
    patch_csm_create_causal_mask_for_1d_position_ids()
=======
>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)
    if args.context_wav is not None and not args.context_wav.is_file():
        raise SystemExit(f"Missing --context-wav: {args.context_wav}")
    if args.context_wav is not None and not args.context_text:
        raise SystemExit("--context-text is required when using --context-wav")

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    model, _tokenizer_backend = FastModel.from_pretrained(
        model_name=model_name,
        max_seq_length=2048,
        dtype=None,
        auto_model=CsmForConditionalGeneration,
        load_in_4bit=False,
    )
    processor = AutoProcessor.from_pretrained(model_name)
    if lora_dir is not None:
        if not lora_dir.is_dir():
            raise ValueError(f"lora_dir is not a directory: {lora_dir}")
        model = PeftModel.from_pretrained(model, str(lora_dir))

    FastModel.for_inference(model)
    model.eval()
    model.to(device_resolved)

<<<<<<< HEAD
    if sync_csm_backbone_audio_embedding_from_depth(model):
        print(
            "Synced backbone audio embeddings from depth decoder (required for unsloth/csm-1b checkpoints).",
            flush=True,
        )

=======
>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)
    # Unsloth replaces depth-decoder forward with (*args, **kwargs), so Transformers 5.5
    # generate() rejects backbone_last_hidden_state in model_kwargs. Training patches restore
    # HF-forward behavior and the embedding clone (in-place row-0 write + PEFT).
    patch_depth_decoder_embedding_clone(model)
    patch_depth_decoder_causal_lm_forward(model)

    return model, processor, device_resolved


def synthesize_csm_to_file(
    *,
    model: Any,
    processor: Any,
    device: str,
    text: str,
    speaker_id: int,
    out: Path,
    max_new_tokens: int,
    context_wav: Path | None = None,
    context_text: str | None = None,
) -> None:
    """Run one generation and write a 24 kHz WAV. Reuses a model from ``load_csm_for_inference``."""
    if context_wav is not None and not context_wav.is_file():
        raise FileNotFoundError(f"Missing context-wav: {context_wav}")
    if context_wav is not None and not (context_text or "").strip():
        raise ValueError("context-text is required when using context-wav")

    sid = str(speaker_id)

    if context_wav is not None:
        ctx_audio, sr = sf.read(str(context_wav), dtype="float32", always_2d=False)
        if sr != 24_000:
            raise ValueError(f"Context WAV must be 24 kHz, got {sr}")
        if ctx_audio.ndim > 1:
            ctx_audio = ctx_audio.mean(axis=1)
        conversation = [
            {
                "role": sid,
                "content": [
                    {"type": "text", "text": context_text},
                    {"type": "audio", "path": np.asarray(ctx_audio, dtype=np.float32)},
                ],
            },
            {"role": sid, "content": [{"type": "text", "text": text}]},
        ]
        inputs = processor.apply_chat_template(
            conversation,
            tokenize=True,
            return_dict=True,
        )
    else:
        conversation = [
            {"role": sid, "content": [{"type": "text", "text": text}]},
        ]
        inputs = processor.apply_chat_template(
            conversation,
            tokenize=True,
            return_dict=True,
        )

    inputs = inputs.to(device)
    with torch.no_grad():
<<<<<<< HEAD
        gen_out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            output_audio=True,
            return_dict_in_generate=False,
        )
    wav = _extract_generated_audio(gen_out).to(torch.float32).cpu()
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    processor.save_audio([wav], str(out))


def main():
    args = parse_args()
    if args.context_wav is not None and not args.context_wav.is_file():
        raise SystemExit(f"Missing --context-wav: {args.context_wav}")
    if args.context_wav is not None and not args.context_text:
        raise SystemExit("--context-text is required when using --context-wav")

    device_arg = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model, processor, device_str = load_csm_for_inference(
        model_name=args.model_name,
        lora_dir=args.lora_dir,
        device=device_arg,
    )
    synthesize_csm_to_file(
        model=model,
        processor=processor,
        device=device_str,
        text=args.text,
        speaker_id=args.speaker_id,
        out=args.out,
        max_new_tokens=args.max_new_tokens,
        context_wav=args.context_wav,
        context_text=args.context_text,
    )
    print(args.out.resolve())


if __name__ == "__main__":
    main()
