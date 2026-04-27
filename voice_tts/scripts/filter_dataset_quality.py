#!/usr/bin/env python3
"""Keep only higher-quality clips: minimum word count and minimum RMS (loudness).

RMS is computed on the current WAV (e.g. after peak normalization). Rewrites
``metadata.csv`` and deletes dropped audio unless ``--keep-removed-audio``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
_KD = _ROOT.parent
for p in (_KD, _KD / "voice_ft", _KD / "voice_tts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import _load_wav_mono_float32  # noqa: E402


def _word_count(text: str) -> int:
    return len(text.split())


def _mono_rms(audio_array) -> float:
    a = np.asarray(audio_array, dtype=np.float64)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a * a)))


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
    p.add_argument("--dataset-dir", type=Path, required=True)
    p.add_argument(
        "--min-words",
        type=int,
        default=9,
        help="Minimum token count (whitespace-split). Default: 9.",
    )
    p.add_argument(
        "--min-rms",
        type=float,
        default=0.08,
        help="Minimum waveform RMS on loaded mono float audio. Default: 0.08.",
    )
    p.add_argument(
        "--keep-removed-audio",
        action="store_true",
        help="Do not delete WAV files for dropped rows.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print keep/drop only; do not change files.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    root = args.dataset_dir.expanduser().resolve()
    meta_path = root / "metadata.csv"
    if not meta_path.is_file():
        raise SystemExit(f"Missing metadata.csv: {meta_path}")

    if args.min_words < 1:
        raise SystemExit("--min-words must be >= 1")
    if args.min_rms <= 0:
        raise SystemExit("--min-rms must be > 0")

    pairs = _read_metadata_rows(meta_path)
    kept: list[tuple[str, str]] = []
    dropped: list[tuple[str, str, int, float]] = []

    for file_name, text in pairs:
        path = root / file_name
        if not path.is_file():
            raise SystemExit(f"Audio file missing: {path}")
        arr, _sr = _load_wav_mono_float32(path)
        wc = _word_count(text)
        rms = _mono_rms(arr)
        if wc >= args.min_words and rms >= args.min_rms:
            kept.append((file_name, text))
        else:
            dropped.append((file_name, text, wc, rms))

    print(
        f"Keep {len(kept)} / {len(pairs)} "
        f"(min_words={args.min_words}, min_rms={args.min_rms})",
        flush=True,
    )
    for fn, _t, wc, rms in dropped[:25]:
        print(f"  drop {fn}  words={wc} rms={rms:.4f}", flush=True)
    if len(dropped) > 25:
        print(f"  ... and {len(dropped) - 25} more", flush=True)

    if not kept:
        raise SystemExit("No clips left; relax --min-words or --min-rms.")

    if args.dry_run:
        return

    for fn, _t, _wc, _rms in dropped:
        path = root / fn
        if not args.keep_removed_audio and path.is_file():
            path.unlink()

    tmp = meta_path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file_name", "text"])
        w.writeheader()
        for file_name, text in kept:
            w.writerow({"file_name": file_name, "text": text})
    tmp.replace(meta_path)
    print(f"Wrote {meta_path} ({len(kept)} rows).", flush=True)


if __name__ == "__main__":
    main()
