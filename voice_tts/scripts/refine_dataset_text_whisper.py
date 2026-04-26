#!/usr/bin/env python3
"""Replace ``metadata.csv`` ``text`` columns using Whisper on each clip (fixes bad YouTube SRT).

Expects the same layout as ``voice_ft.common.load_local_audio_metadata_dir``:
``data_dir/metadata.csv`` with ``file_name``, ``text`` and WAV paths relative to ``data_dir``.

  pip install -r ../requirements-whisper-refine.txt
  python3 scripts/refine_dataset_text_whisper.py --data-dir ./srt_dataset_out

Use ``--write metadata_whisper.csv`` to keep the original CSV; default is in-place overwrite.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
import unicodedata
from pathlib import Path


def _normalize_whisper_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.split())
    return s.strip()


def _load_metadata_rows(meta_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with meta_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Empty CSV: {meta_path}")
        fieldnames = list(reader.fieldnames)
        fn_key = next(
            (k for k in reader.fieldnames if k.strip().lower() == "file_name"),
            None,
        )
        text_key = next(
            (k for k in reader.fieldnames if k.strip().lower() == "text"),
            None,
        )
        if not fn_key or not text_key:
            raise ValueError(f"{meta_path} needs file_name and text columns")
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append(dict(row))
    return fieldnames, rows


def _write_metadata(meta_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def refine_dataset(
    data_dir: Path,
    *,
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "default",
    language: str | None = "en",
    vad_filter: bool = False,
    fallback_original: bool = True,
    metadata_out: Path | None = None,
) -> dict:
    """Transcribe each clip; update text. Returns counts."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as ex:
        raise RuntimeError(
            "faster-whisper is required: pip install -r voice_tts/requirements-whisper-refine.txt"
        ) from ex

    root = data_dir.resolve()
    meta_in = root / "metadata.csv"
    if not meta_in.is_file():
        raise FileNotFoundError(meta_in)

    fieldnames, rows = _load_metadata_rows(meta_in)
    fn_key = next(k for k in fieldnames if k.strip().lower() == "file_name")
    text_key = next(k for k in fieldnames if k.strip().lower() == "text")

    if device == "auto":
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
    if compute_type == "default":
        compute_type = "float16" if device == "cuda" else "int8"

    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None  # type: ignore[misc, assignment]

    updated = 0
    kept_fallback = 0
    empty_drop = 0
    row_iter = tqdm(rows, desc="Whisper", unit="clip") if tqdm else rows
    for row in row_iter:
        rel = (row.get(fn_key) or "").strip()
        old_text = (row.get(text_key) or "").strip()
        if not rel:
            continue
        wav = root / rel
        if not wav.is_file():
            raise FileNotFoundError(wav)

        segs, _info = model.transcribe(
            str(wav),
            language=language,
            vad_filter=vad_filter,
            word_timestamps=False,
        )
        parts: list[str] = []
        for seg in segs:
            t = getattr(seg, "text", "") or ""
            t = re.sub(r"^\s*\[[^\]]*\]\s*", "", t)
            parts.append(t)
        new_text = _normalize_whisper_text(" ".join(parts))

        if new_text:
            row[text_key] = new_text
            updated += 1
        elif fallback_original and old_text:
            kept_fallback += 1
        else:
            row[text_key] = ""
            empty_drop += 1

    out_path = metadata_out if metadata_out is not None else meta_in
    _write_metadata(out_path, fieldnames, rows)

    return {
        "rows": len(rows),
        "transcribed": updated,
        "fallback_original": kept_fallback,
        "cleared": empty_drop,
        "metadata_written": str(out_path),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Folder with metadata.csv and audio/ (or paths in CSV)",
    )
    p.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Output CSV path (default: overwrite data-dir/metadata.csv)",
    )
    p.add_argument(
        "--backup",
        action="store_true",
        help="If overwriting, copy metadata.csv to metadata.csv.bak first",
    )
    p.add_argument(
        "--model",
        default="base",
        help="faster-whisper model: tiny, base, small, medium, large-v3, ...",
    )
    p.add_argument(
        "--device",
        default="auto",
        help="cuda, cpu, or auto",
    )
    p.add_argument(
        "--compute-type",
        default="default",
        help="float16, int8, int8_float16, ... (default: float16 on cuda else int8)",
    )
    p.add_argument(
        "--language",
        default="en",
        help="Whisper language code, or 'auto' for detection",
    )
    p.add_argument(
        "--vad-filter",
        action="store_true",
        help="Enable VAD (can silence very short clips; off by default)",
    )
    p.add_argument(
        "--no-fallback",
        action="store_true",
        help="If Whisper returns empty, clear text instead of keeping the old caption",
    )
    args = p.parse_args()

    root = args.data_dir.expanduser().resolve()
    meta_in = root / "metadata.csv"
    out_path = args.write.expanduser().resolve() if args.write else meta_in

    if args.backup and out_path == meta_in and meta_in.is_file():
        bak = meta_in.with_suffix(meta_in.suffix + ".bak")
        shutil.copy2(meta_in, bak)
        print(f"Backup: {bak}", flush=True)

    lang = None if args.language.lower() == "auto" else args.language
    summary = refine_dataset(
        root,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=lang,
        vad_filter=args.vad_filter,
        fallback_original=not args.no_fallback,
        metadata_out=out_path,
    )

    print(
        f"Transcribed {summary['transcribed']}/{summary['rows']} rows; "
        f"fallback={summary['fallback_original']}; cleared={summary['cleared']}",
        flush=True,
    )
    print(f"Wrote {summary['metadata_written']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
