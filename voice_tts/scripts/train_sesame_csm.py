#!/usr/bin/env python3
"""Fine-tune Sesame CSM-1B (TTS) with Unsloth + LoRA on local audio+text data.

Expects the same layout as voice_ft/dataset-ui exports:
  dataset_dir/metadata.csv  (file_name, text)
  dataset_dir/audio/*.wav

Audio is loaded at 24 kHz (CSM). See Unsloth notebook:
https://github.com/unslothai/notebooks/blob/main/nb/Sesame_CSM_(1B)-TTS.ipynb
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from pathlib import Path

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

_ROOT = Path(__file__).resolve().parent.parent
_KD = _ROOT.parent
if str(_KD) not in sys.path:
    sys.path.insert(0, str(_KD))
if str(_KD / "voice_tts") not in sys.path:
    sys.path.insert(0, str(_KD / "voice_tts"))

import torch
from transformers import AutoProcessor, CsmForConditionalGeneration, Trainer, TrainingArguments
from unsloth import FastModel, is_bfloat16_supported

from csm_dataset import build_csm_processed_dataset, load_local_csm_raw
from csm_model_patches import (
    patch_csm_create_causal_mask_for_1d_position_ids,
    patch_depth_decoder_causal_lm_forward,
    patch_depth_decoder_embedding_clone,
    sync_csm_backbone_audio_embedding_from_depth,
)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Root with metadata.csv and audio/",
    )
    p.add_argument("--model-name", default="unsloth/csm-1b")
    p.add_argument("--speaker-id", default="0", help="Single-speaker id string for CSM")
    p.add_argument("--output-dir", default="outputs_csm")
    p.add_argument("--lora-dir", default="sesame_csm_lora")
    p.add_argument("--max-steps", type=int, default=60)
    p.add_argument(
        "--num-train-epochs",
        type=int,
        default=None,
        help="If set, full epochs and ignores --max-steps",
    )
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--warmup-steps", type=int, default=5)
    p.add_argument("--lora-r", type=int, default=32)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--load-in-4bit", action="store_true")
    p.add_argument("--no-save-lora", action="store_true")
    p.add_argument(
        "--save-steps",
        type=int,
        default=None,
        help="If set, write Trainer checkpoints under --output-dir every N global steps (for resume).",
    )
    p.add_argument(
        "--save-total-limit",
        type=int,
        default=5,
        help="Max checkpoints to keep when --save-steps is set (oldest deleted).",
    )
    p.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Resume from a Trainer checkpoint dir, e.g. outputs_csm/checkpoint-500",
    )
    p.add_argument(
        "--audio-peak-norm",
        type=float,
        default=None,
        metavar="MAX",
        help="Normalize each clip: scale so max |sample| is MAX (e.g. 0.99). Default: no normalization.",
    )
    p.add_argument(
        "--min-audio-rms",
        type=float,
        default=None,
        help="Drop clips with RMS below this (on loaded mono audio, before peak norm). Try 0.005–0.02.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    patch_csm_create_causal_mask_for_1d_position_ids()
    if not args.dataset_dir.is_dir():
        raise SystemExit(f"--dataset-dir is not a directory: {args.dataset_dir}")
    if args.save_steps is not None and args.save_steps < 1:
        raise SystemExit("--save-steps must be >= 1")
    if args.resume is not None:
        ckpt = args.resume.expanduser().resolve()
        if not ckpt.is_dir():
            raise SystemExit(f"--resume is not a directory: {ckpt}")
        if not (ckpt / "trainer_state.json").is_file():
            raise SystemExit(
                f"--resume must be a Hugging Face Trainer checkpoint (missing trainer_state.json): {ckpt}"
            )
        args.resume = ckpt

    # Second return from FastModel is a tokenizer backend, not CsmProcessor — it cannot
    # build audio features. Use AutoProcessor like the official Sesame notebook data cell.
    model, _tokenizer_backend = FastModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=2048,
        dtype=None,
        auto_model=CsmForConditionalGeneration,
        load_in_4bit=args.load_in_4bit,
    )
    processor = AutoProcessor.from_pretrained(args.model_name)
    model = FastModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        use_rslora=False,
        loftq_config=None,
    )
    if sync_csm_backbone_audio_embedding_from_depth(model):
        print(
            "Synced backbone audio embeddings from depth decoder (unsloth/csm-1b checkpoint).",
            flush=True,
        )
    if patch_depth_decoder_embedding_clone(model) == 0:
        print(
            "Warning: depth-decoder embedding clone patch did not apply "
            "(no CsmDepthDecoderModel in module tree). Training may fail with in-place grad errors.",
            flush=True,
        )
    if patch_depth_decoder_causal_lm_forward(model) == 0:
        print(
            "Warning: depth-decoder CausalLM forward patch did not apply "
            "(no CsmDepthDecoderForCausalLM in module tree). Training may fail when cache_position is None.",
            flush=True,
        )

    raw_ds = load_local_csm_raw(
        args.dataset_dir,
        speaker_id=args.speaker_id,
        peak_norm_max=args.audio_peak_norm,
        min_rms=args.min_audio_rms,
    )
    processed_ds = build_csm_processed_dataset(raw_ds, processor)

    use_epochs = args.num_train_epochs is not None
    max_steps = -1 if use_epochs else args.max_steps
    num_train_epochs = args.num_train_epochs if use_epochs else 1.0

    if torch.cuda.is_available():
        gpu_stats = torch.cuda.get_device_properties(0)
        start_gpu_memory = round(torch.cuda.max_memory_reserved() / 1024**3, 3)
        max_mem_gb = round(gpu_stats.total_memory / 1024**3, 3)
        print(f"GPU = {gpu_stats.name}. Max memory = {max_mem_gb} GB.")
        print(f"{start_gpu_memory} GB of memory reserved.")
    else:
        print("No CUDA GPU detected; training will be very slow on CPU.")

    ta_kw = dict(
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_steps=args.warmup_steps,
        max_steps=max_steps,
        num_train_epochs=num_train_epochs,
        learning_rate=args.lr,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.001,
        lr_scheduler_type="linear",
        seed=args.seed,
        output_dir=args.output_dir,
        report_to="none",
        remove_unused_columns=False,
    )
    if args.save_steps is not None:
        ta_kw["save_strategy"] = "steps"
        ta_kw["save_steps"] = args.save_steps
        ta_kw["save_total_limit"] = args.save_total_limit
    else:
        ta_kw["save_strategy"] = "no"

    training_args = TrainingArguments(**ta_kw)
    trainer_kw = dict(
        model=model,
        train_dataset=processed_ds,
        args=training_args,
    )
    if "processing_class" in inspect.signature(Trainer.__init__).parameters:
        trainer_kw["processing_class"] = processor
    else:
        trainer_kw["tokenizer"] = processor
    trainer = Trainer(**trainer_kw)
    trainer.model_accepts_loss_kwargs = False

    resume_kw = {}
    if args.resume is not None:
        resume_kw["resume_from_checkpoint"] = str(args.resume)
        print(f"Resuming from {args.resume}", flush=True)

    stats = trainer.train(**resume_kw)
    print(f"Training finished in {stats.metrics.get('train_runtime', 0):.1f} s.")

    if not args.no_save_lora:
        out = Path(args.lora_dir)
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(out)
        processor.save_pretrained(out)
        print(f"Saved LoRA + processor to {out.resolve()}")


if __name__ == "__main__":
    main()
