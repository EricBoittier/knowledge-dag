#!/usr/bin/env python3
"""Fine-tune Whisper (default: openai/whisper-tiny.en) with Unsloth + LoRA."""

from __future__ import annotations

import os

# Whisper init can trigger torch.compile on sinusoids; Inductor then needs Python.h.
# If python3.12-devel (or your training interpreter's -devel) isn't installed, disable Dynamo.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

import argparse
import inspect
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import torch
from transformers import Seq2SeqTrainer, Seq2SeqTrainingArguments

from common import (
    WHISPER_MODEL_ID,
    DataCollatorSpeechSeq2SeqWithPadding,
    apply_lora,
    build_processed_splits,
    build_processed_splits_local_dir,
    configure_generation_english,
    load_model_and_tokenizer,
    make_compute_metrics,
)
from unsloth import is_bf16_supported


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--model-name",
        default=WHISPER_MODEL_ID,
        help="Base Whisper checkpoint on the Hub",
    )
    p.add_argument(
        "--dataset",
        default="MrDragonFox/Elise",
        help="HF dataset id (ignored if --dataset-dir is set)",
    )
    p.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Local AudioFolder root (metadata.csv + audio/). Mutually exclusive with Hub --dataset.",
    )
    p.add_argument("--dataset-split", default="train", help="Split name to load")
    p.add_argument("--test-size", type=float, default=0.06)
    p.add_argument("--output-dir", default="outputs", help="Trainer checkpoints")
    p.add_argument(
        "--lora-dir",
        default="whisper_lora",
        help="Where to save adapter + processor after training",
    )
    p.add_argument("--max-steps", type=int, default=60)
    p.add_argument(
        "--num-train-epochs",
        type=int,
        default=None,
        help="If set, runs full epochs and ignores --max-steps",
    )
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--warmup-steps", type=int, default=5)
    p.add_argument("--eval-steps", type=int, default=5)
    p.add_argument("--lora-r", type=int, default=64)
    p.add_argument("--lora-alpha", type=int, default=64)
    p.add_argument("--seed", type=int, default=3407)
    p.add_argument("--load-in-4bit", action="store_true")
    p.add_argument(
        "--no-save-lora",
        action="store_true",
        help="Skip writing adapter + processor to --lora-dir",
    )
    args = p.parse_args()
    if args.dataset_dir is not None and not args.dataset_dir.is_dir():
        p.error(f"--dataset-dir is not a directory: {args.dataset_dir}")
    return args


def main():
    args = parse_args()
    model, tokenizer = load_model_and_tokenizer(
        model_name=args.model_name,
        load_in_4bit=args.load_in_4bit,
    )
    model = apply_lora(model, r=args.lora_r, lora_alpha=args.lora_alpha)
    configure_generation_english(model)

    if args.dataset_dir is not None:
        train_dataset, test_dataset = build_processed_splits_local_dir(
            args.dataset_dir,
            args.test_size,
            tokenizer,
            seed=args.seed,
        )
    else:
        train_dataset, test_dataset = build_processed_splits(
            args.dataset,
            args.dataset_split,
            args.test_size,
            tokenizer,
        )

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
        start_gpu_memory = 0.0
        max_mem_gb = 0.0
        print("No CUDA GPU detected; training will be very slow on CPU.")

    training_args = Seq2SeqTrainingArguments(
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_steps=args.warmup_steps,
        max_steps=max_steps,
        num_train_epochs=num_train_epochs,
        learning_rate=args.lr,
        logging_steps=1,
        optim="adamw_8bit",
        fp16=not is_bf16_supported(),
        bf16=is_bf16_supported(),
        weight_decay=0.001,
        remove_unused_columns=False,
        lr_scheduler_type="linear",
        label_names=["labels"],
        eval_steps=args.eval_steps,
        eval_strategy="steps",
        seed=args.seed,
        output_dir=args.output_dir,
        report_to="none",
    )
    trainer_kw = dict(
        model=model,
        train_dataset=train_dataset,
        data_collator=DataCollatorSpeechSeq2SeqWithPadding(processor=tokenizer),
        eval_dataset=test_dataset,
        compute_metrics=make_compute_metrics(tokenizer),
        args=training_args,
    )
    proc = tokenizer.feature_extractor
    if "processing_class" in inspect.signature(Seq2SeqTrainer.__init__).parameters:
        trainer_kw["processing_class"] = proc
    else:
        trainer_kw["tokenizer"] = proc
    trainer = Seq2SeqTrainer(**trainer_kw)
    # Whisper forward + Transformers 5.5 `num_items_in_batch` can produce a non-tensor loss;
    # Unsloth's patched training_step then fails on `.mean()`.
    trainer.model_accepts_loss_kwargs = False

    stats = trainer.train()

    if torch.cuda.is_available():
        used = round(torch.cuda.max_memory_reserved() / 1024**3, 3)
        delta = round(used - start_gpu_memory, 3)
        pct = round(used / max_mem_gb * 100, 3) if max_mem_gb else 0.0
        print(f"{stats.metrics['train_runtime']:.1f} s training.")
        print(f"Peak reserved memory = {used} GB (+{delta} GB). {pct}% of GPU cap.")
    else:
        print(f"{stats.metrics['train_runtime']:.1f} s training.")

    if not args.no_save_lora:
        out = Path(args.lora_dir)
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(out)
        tokenizer.save_pretrained(out)
        print(f"Saved LoRA + processor to {out.resolve()}")


if __name__ == "__main__":
    main()
