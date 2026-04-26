"""Shared helpers for Whisper fine-tuning (English-only tiny)."""

from __future__ import annotations

import csv
import hashlib
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Union

import evaluate
import numpy as np
import torch
import tqdm
from datasets import Audio, Dataset, DatasetInfo, Features, Sequence, Value, load_dataset
from datasets.arrow_dataset import OptimizedTypedSequence, _fix_for_backward_compatible_features
from datasets.table import InMemoryTable
from transformers import WhisperForConditionalGeneration

# English-only checkpoint: smaller vocab / decoder than multilingual whisper-tiny.
WHISPER_MODEL_ID = "openai/whisper-tiny.en"


def load_model_and_tokenizer(
    *,
    model_name: str = WHISPER_MODEL_ID,
    load_in_4bit: bool = False,
    whisper_language: str = "English",
    whisper_task: str = "transcribe",
):
    from unsloth import FastModel

    model, tokenizer = FastModel.from_pretrained(
        model_name=model_name,
        dtype=None,
        load_in_4bit=load_in_4bit,
        auto_model=WhisperForConditionalGeneration,
        whisper_language=whisper_language,
        whisper_task=whisper_task,
    )
    return model, tokenizer


def apply_lora(
    model,
    *,
    r: int = 64,
    lora_alpha: int = 64,
    target_modules: list[str] | None = None,
):
    if target_modules is None:
        target_modules = ["q_proj", "v_proj"]
    from unsloth import FastModel

    return FastModel.get_peft_model(
        model,
        r=r,
        target_modules=target_modules,
        lora_alpha=lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
        use_rslora=False,
        loftq_config=None,
        task_type=None,
    )


def configure_generation_english(model) -> None:
    model.generation_config.language = "<|en|>"
    model.generation_config.task = "transcribe"
    model.config.suppress_tokens = []
    model.generation_config.forced_decoder_ids = None


def _resample_linear_mono(x: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr or len(x) == 0:
        return x.astype(np.float32, copy=False)
    old_idx = np.linspace(0, len(x) - 1, num=len(x), dtype=np.float64)
    new_len = max(1, int(round(len(x) * target_sr / orig_sr)))
    new_idx = np.linspace(0, len(x) - 1, num=new_len, dtype=np.float64)
    return np.interp(new_idx, old_idx, x.astype(np.float64)).astype(np.float32)


def _load_wav_mono_float32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype="<f4").astype(np.float32)
    else:
        raise ValueError(
            f"Expected 16-bit PCM or 32-bit float WAV (got {sw}-byte samples): {path}"
        )
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x.astype(np.float32), int(sr)


def _dataset_from_local_audio_examples(examples: list[dict]) -> Dataset:
    """HF Dataset for local clips without ``Audio`` (avoids torchcodec). Explicit ``fingerprint`` avoids Python 3.14 + dill breakage in ``generate_fingerprint``."""
    features = Features(
        {
            "audio": Features(
                {
                    "array": Sequence(Value("float32")),
                    "sampling_rate": Value("int32"),
                }
            ),
            "text": Value("string"),
        }
    )
    mapping = {k: [r[k] for r in examples] for k in examples[0]}
    features = _fix_for_backward_compatible_features(features)
    arrow_typed_mapping: dict = {}
    for col, data in mapping.items():
        arrow_typed_mapping[col] = OptimizedTypedSequence(
            features.encode_column(data, col),
            type=features[col],
            col=col,
        )
    pa_table = InMemoryTable.from_pydict(arrow_typed_mapping)
    info = DatasetInfo(features=features)
    h = hashlib.sha256()
    for ex in examples:
        h.update(ex["text"].encode("utf-8"))
        h.update(np.asarray(ex["audio"]["array"], dtype=np.float32).tobytes())
        h.update(str(int(ex["audio"]["sampling_rate"])).encode("ascii"))
    return Dataset(pa_table, info=info, fingerprint=h.hexdigest())


def load_local_audio_metadata_dir(
    data_dir: Path | str,
    *,
    target_sr: int = 16000,
) -> Dataset:
    """Load dataset from AudioFolder-style layout: metadata.csv + audio files.

    Expects metadata.csv with columns file_name,text (paths relative to data_dir).
    WAV files are mixed to mono and resampled to target_sr when needed.
    """
    root = Path(data_dir).resolve()
    meta_path = root / "metadata.csv"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing metadata.csv under {root}")

    rows: list[tuple[str, str]] = []
    with meta_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Empty or invalid CSV: {meta_path}")
        fn_key = next(
            (k for k in reader.fieldnames if k.strip().lower() == "file_name"),
            None,
        )
        text_key = next(
            (k for k in reader.fieldnames if k.strip().lower() == "text"),
            None,
        )
        if not fn_key or not text_key:
            raise ValueError(
                f"metadata.csv must include file_name and text columns: {meta_path}"
            )
        for row in reader:
            fn = (row.get(fn_key) or "").strip()
            text = (row.get(text_key) or "").strip()
            if not fn or not text:
                continue
            rows.append((fn, text))

    if not rows:
        raise ValueError(f"No valid rows in {meta_path}")

    examples: list[dict] = []
    for file_name, text in rows:
        path = root / file_name
        if not path.is_file():
            raise FileNotFoundError(f"Audio file missing: {path}")
        arr, sr = _load_wav_mono_float32(path)
        arr = _resample_linear_mono(arr, sr, target_sr)
        examples.append(
            {
                "audio": {"array": arr, "sampling_rate": int(target_sr)},
                "text": text,
            }
        )

    return _dataset_from_local_audio_examples(examples)


def _adaptive_train_test_split(
    dataset: Dataset,
    test_size: float,
    *,
    seed: int = 3407,
) -> tuple[Dataset, Dataset]:
    n = len(dataset)
    if n == 0:
        raise ValueError("Dataset is empty")
    if n == 1:
        return dataset, dataset
    n_test = max(1, min(n - 1, int(round(n * test_size))))
    split = dataset.train_test_split(test_size=n_test, seed=seed)
    return split["train"], split["test"]


def make_formatting_fn(tokenizer):
    def formatting_prompts_func(example):
        audio_arrays = example["audio"]["array"]
        sampling_rate = example["audio"]["sampling_rate"]
        features = tokenizer.feature_extractor(
            audio_arrays,
            sampling_rate=sampling_rate,
        )
        tokenized_text = tokenizer.tokenizer(example["text"])
        return {
            "input_features": features.input_features[0],
            "labels": tokenized_text.input_ids,
        }

    return formatting_prompts_func


def _format_split(dataset: Dataset, tokenizer, desc: str):
    fmt = make_formatting_fn(tokenizer)
    return [fmt(ex) for ex in tqdm.tqdm(dataset, desc=desc)]


def build_processed_splits(
    dataset_id: str,
    split: str,
    test_size: float,
    tokenizer,
    *,
    audio_sr: int = 16000,
):
    dataset = load_dataset(dataset_id, split=split)
    dataset = dataset.cast_column("audio", Audio(sampling_rate=audio_sr))
    train_raw, test_raw = _adaptive_train_test_split(dataset, test_size)
    train_dataset = _format_split(train_raw, tokenizer, "Train split")
    test_dataset = _format_split(test_raw, tokenizer, "Test split")
    return train_dataset, test_dataset


def build_processed_splits_local_dir(
    data_dir: Path | str,
    test_size: float,
    tokenizer,
    *,
    audio_sr: int = 16000,
    seed: int = 3407,
):
    """Build train/test feature lists from a local AudioFolder-style directory."""
    dataset = load_local_audio_metadata_dir(data_dir, target_sr=audio_sr)
    train_raw, test_raw = _adaptive_train_test_split(
        dataset,
        test_size,
        seed=seed,
    )
    train_dataset = _format_split(train_raw, tokenizer, "Train split")
    test_dataset = _format_split(test_raw, tokenizer, "Test split")
    return train_dataset, test_dataset


def make_compute_metrics(tokenizer):
    metric = evaluate.load("wer")

    def compute_metrics(pred):
        pred_logits = pred.predictions[0]
        label_ids = pred.label_ids.copy()
        label_ids[label_ids == -100] = tokenizer.pad_token_id
        pred_ids = np.argmax(pred_logits, axis=-1)
        pred_str = tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
        label_str = tokenizer.batch_decode(label_ids, skip_special_tokens=True)
        wer = 100 * metric.compute(predictions=pred_str, references=label_str)
        return {"wer": wer}

    return compute_metrics


@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    processor: Any

    def __call__(
        self,
        features: List[Dict[str, Union[List[int], torch.Tensor]]],
    ) -> Dict[str, torch.Tensor]:
        input_features = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(
            input_features,
            return_tensors="pt",
        )
        label_features = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(
            label_features,
            return_tensors="pt",
        )
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1),
            -100,
        )
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            labels = labels[:, 1:]
        batch["labels"] = labels
        return batch
