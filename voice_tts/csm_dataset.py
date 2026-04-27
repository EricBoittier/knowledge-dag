"""Build a Hugging Face dataset for Sesame CSM-1B fine-tuning (Unsloth notebook logic)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import torch
from datasets import Dataset, DatasetInfo
from datasets.fingerprint import generate_random_fingerprint
from datasets.table import InMemoryTable
from tqdm import tqdm

_KD = Path(__file__).resolve().parent.parent
if str(_KD) not in sys.path:
    sys.path.insert(0, str(_KD))
if str(_KD / "voice_ft") not in sys.path:
    sys.path.insert(0, str(_KD / "voice_ft"))

from common import load_local_audio_metadata_dir  # noqa: E402


def _mono_rms(audio_array) -> float:
    a = np.asarray(audio_array, dtype=np.float64)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a * a)))


def _peak_normalize(audio_array, peak_limit: float) -> np.ndarray:
    """Scale so max(|x|) == peak_limit; leaves near-silent audio unchanged."""
    a = np.asarray(audio_array, dtype=np.float32)
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak < 1e-12:
        return a
    scale = peak_limit / peak
    return (a * scale).astype(np.float32, copy=False)


def _tensor_batch_to_hf_dataset(rows: list[dict]) -> Dataset:
    """Avoid ``Dataset.from_list`` on Python 3.14 (dill / ``Pickler._batch_setitems``)."""

    def to_plain(v):
        if isinstance(v, torch.Tensor):
            x = v.detach().cpu()
            if x.ndim == 0:
                return x.item()
            return x.numpy().tolist()
        if isinstance(v, np.ndarray):
            if v.ndim == 0:
                return v.item()
            return v.tolist()
        return v

    plain = [{k: to_plain(v) for k, v in r.items()} for r in rows]
    pa_table = InMemoryTable(pa.Table.from_pylist(plain))
    return Dataset(
        pa_table,
        info=DatasetInfo(),
        fingerprint=generate_random_fingerprint(),
    )


def load_local_csm_raw(
    data_dir: Path | str,
    *,
    speaker_id: str = "0",
    peak_norm_max: float | None = None,
    min_rms: float | None = None,
):
    """Load metadata.csv + audio/ at 24 kHz; add ``source`` for CSM.

    ``min_rms`` drops clips whose RMS is below the threshold (evaluated on loaded
    audio before any normalization). ``peak_norm_max`` in (0, 1] scales each clip
    so max(|sample|) equals that value (typical: 0.99).
    """
    root = Path(data_dir).resolve()
    ds = load_local_audio_metadata_dir(root, target_sr=24_000)

    if min_rms is not None and min_rms > 0:

        def _loud_enough(ex: dict) -> bool:
            return _mono_rms(ex["audio"]["array"]) >= min_rms

        ds = ds.filter(_loud_enough)
        if len(ds) == 0:
            raise ValueError(
                "All clips were removed by --min-audio-rms; lower the threshold or check your WAVs."
            )

    if peak_norm_max is not None:
        lim = float(peak_norm_max)
        if not (0.0 < lim <= 1.0):
            raise ValueError("peak_norm_max must be in (0, 1], e.g. 0.99")

        def _norm_peak(ex: dict) -> dict:
            arr = _peak_normalize(ex["audio"]["array"], lim)
            return {
                **ex,
                "audio": {
                    "array": arr,
                    "sampling_rate": ex["audio"]["sampling_rate"],
                },
            }

        ds = ds.map(_norm_peak)

    n = len(ds)
    return ds.add_column("source", [speaker_id] * n)


def preprocess_csm_example(example: dict, processor, *, speaker_key: str = "source") -> dict | None:
    """One row → model inputs (tensors). Returns None on failure."""
    conversation = [
        {
            "role": str(example[speaker_key]),
            "content": [
                {"type": "text", "text": example["text"]},
                {
                    "type": "audio",
                    "path": np.asarray(example["audio"]["array"], dtype=np.float32),
                },
            ],
        }
    ]
    try:
        model_inputs = processor.apply_chat_template(
            conversation,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            processor_kwargs={
                "output_labels": True,
                "text_kwargs": {
                    "padding": "max_length",
                    "max_length": 256,
                    "pad_to_multiple_of": 8,
                    "padding_side": "right",
                },
                "audio_kwargs": {
                    "sampling_rate": 24_000,
                    "max_length": 240_001,
                    "padding": "max_length",
                },
                "common_kwargs": {"return_tensors": "pt"},
            },
        )
    except Exception:
        return None

    required_keys = [
        "input_ids",
        "attention_mask",
        "labels",
        "input_values",
        "input_values_cutoffs",
    ]
    processed_example = {}
    for key in required_keys:
        if key not in model_inputs:
            return None
        value = model_inputs[key][0]
        processed_example[key] = value

    if not all(isinstance(processed_example[k], torch.Tensor) for k in processed_example):
        return None
    return processed_example


def build_csm_processed_dataset(raw_ds: Dataset, processor, *, desc: str = "Preprocess CSM") -> Dataset:
    rows: list[dict] = []
    for i in tqdm(range(len(raw_ds)), desc=desc):
        ex = raw_ds[i]
        out = preprocess_csm_example(ex, processor)
        if out is not None:
            rows.append(out)
    if not rows:
        raise ValueError("No examples survived preprocessing (check audio length / text).")
    return _tensor_batch_to_hf_dataset(rows)
