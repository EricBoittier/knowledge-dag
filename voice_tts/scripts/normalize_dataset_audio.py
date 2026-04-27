#!/usr/bin/env python3
"""Peak-normalize WAVs under a dataset dir, optionally drop quiet clips, rewrite metadata.csv.

Layout: ``dataset_dir/metadata.csv`` (file_name, text) and paths relative to dataset_dir.

Quiet clips are judged on the **original** float audio before normalization. Removed rows
are dropped from ``metadata.csv``; their WAV files are deleted unless ``--keep-removed-audio``.

After this, training does not need ``--audio-peak-norm`` / ``--min-audio-rms`` for the same effect.
"""

from __future__ import annotations

import argparse
import csv
import sys
import wave
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
_KD = _ROOT.parent
for p in (_KD, _KD / "voice_ft", _KD / "voice_tts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import _load_wav_mono_float32  # noqa: E402
from csm_dataset import _mono_rms, _peak_normalize  # noqa: E402


def _write_wav_mono_16bit(path: Path, arr: np.ndarray, sr: int) -> None:
    x = np.clip(np.asarray(arr, dtype=np.float64), -1.0, 1.0)
    pcm = np.round(x * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())


def _read_metadata_rows(meta_path: Path) -> list[tuple[str, str]]:
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
    return rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Root with metadata.csv and audio/",
    )
    p.add_argument(
        "--peak-norm",
        type=float,
        default=0.99,
        help="Scale each kept clip so max |sample| is this (default: 0.99).",
    )
    p.add_argument(
        "--min-rms",
        type=float,
        default=None,
        help="Drop clips with RMS below this (before peak norm). Example: 0.005–0.02.",
    )
    p.add_argument(
        "--keep-removed-audio",
        action="store_true",
        help="Do not delete WAV files for dropped rows (metadata still updated).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only; do not write files or metadata.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    root = args.dataset_dir.expanduser().resolve()
    meta_path = root / "metadata.csv"
    if not meta_path.is_file():
        raise SystemExit(f"Missing metadata.csv: {meta_path}")

    lim = float(args.peak_norm)
    if not (0.0 < lim <= 1.0):
        raise SystemExit("--peak-norm must be in (0, 1]")

    min_rms = args.min_rms
    if min_rms is not None and min_rms <= 0:
        raise SystemExit("--min-rms must be positive when set")

    pairs = _read_metadata_rows(meta_path)
    kept_rows: list[tuple[str, str, np.ndarray, int]] = []
    removed: list[tuple[str, str, float]] = []
    for file_name, text in pairs:
        path = root / file_name
        arr, sr = _load_wav_mono_float32(path)
        rms = _mono_rms(arr)
        if min_rms is not None and rms < min_rms:
            removed.append((file_name, text, rms))
        else:
            kept_rows.append((file_name, text, arr, sr))

    print(
        f"Kept {len(kept_rows)} / {len(pairs)} clips"
        + (f"; removed {len(removed)} below RMS {min_rms}" if min_rms else ""),
        flush=True,
    )
    for fn, _t, rms in removed[:20]:
        print(f"  drop {fn}  rms={rms:.6f}", flush=True)
    if len(removed) > 20:
        print(f"  ... and {len(removed) - 20} more", flush=True)

    if not kept_rows:
        raise SystemExit("No clips left after filtering; lower --min-rms.")

    if args.dry_run:
        return

    for file_name, _text, arr, sr in kept_rows:
        path = root / file_name
        out = _peak_normalize(arr, lim)
        _write_wav_mono_16bit(path, out, sr)

    for file_name, _text, _rms in removed:
        path = root / file_name
        if not args.keep_removed_audio and path.is_file():
            path.unlink()

    tmp = meta_path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file_name", "text"])
        w.writeheader()
        for file_name, text, _a, _s in kept_rows:
            w.writerow({"file_name": file_name, "text": text})
    tmp.replace(meta_path)
    print(f"Wrote {meta_path} ({len(kept_rows)} rows).", flush=True)


if __name__ == "__main__":
    main()
