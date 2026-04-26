#!/usr/bin/env python3
"""
Text-to-speech for cast / character workflows using reference audio (voice cloning).

Uses Coqui XTTS v2: each character in the roster supplies one or more WAV clips;
synthesis conditions on those clips so lines sound like that character.

Install (separate venv recommended):
  pip install -r voice_tts/requirements-tts.txt

Examples:
  python3 scripts/synthesize.py --roster ../characters.yaml \\
    --character hero --text "Not today." --out ../out/hero_line.wav

  python3 scripts/synthesize.py --roster ../characters.yaml \\
    --dialogue ../dialogue.json --out-dir ../out/lines --concat-out ../out/scene.wav
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as e:
        raise SystemExit("PyYAML is required for .yaml rosters: pip install PyYAML") from e
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Roster root must be a mapping")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Roster root must be a mapping")
    return data


def load_roster(path: Path) -> dict[str, Any]:
    suf = path.suffix.lower()
    if suf in (".yaml", ".yml"):
        return _load_yaml(path)
    if suf == ".json":
        return _load_json(path)
    raise SystemExit(f"Unsupported roster format: {path} (use .yaml or .json)")


def parse_roster(raw: dict[str, Any], roster_path: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    default_lang = str(raw.get("default_language") or "en")
    chars = raw.get("characters")
    if not isinstance(chars, dict) or not chars:
        raise ValueError("Roster must contain a non-empty 'characters' mapping")
    base = roster_path.parent.resolve()
    out: dict[str, dict[str, Any]] = {}
    for cid, spec in chars.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Character {cid!r}: expected mapping")
        key = str(cid).strip()
        if not key:
            continue
        refs: list[str] = []
        if "reference_wav" in spec and spec["reference_wav"]:
            refs.append(str(spec["reference_wav"]))
        for extra in spec.get("reference_wavs") or []:
            refs.append(str(extra))
        if not refs:
            raise ValueError(f"Character {key!r}: set reference_wav or reference_wavs")
        resolved = []
        for r in refs:
            p = Path(r)
            if not p.is_absolute():
                p = (base / p).resolve()
            if not p.is_file():
                raise FileNotFoundError(f"Missing reference audio for {key}: {p}")
            resolved.append(str(p))
        lang = str(spec.get("language") or default_lang)
        out[key] = {"reference_wavs": resolved, "language": lang}
    return default_lang, out


def _ensure_tts_class():
    try:
        from TTS.api import TTS
    except ImportError as e:
        raise SystemExit(
            "Coqui TTS is not installed. Run:\n"
            "  pip install -r voice_tts/requirements-tts.txt\n"
            "(Use a virtualenv; GPU + CUDA PyTorch recommended.)"
        ) from e
    return TTS


def synthesize_to_file(
    tts,
    text: str,
    speaker_wavs: list[str],
    language: str,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wav_arg: str | list[str] = speaker_wavs[0] if len(speaker_wavs) == 1 else speaker_wavs
    tts.tts_to_file(
        text=text,
        file_path=str(out_path),
        speaker_wav=wav_arg,
        language=language,
    )


def concat_wavs(paths: list[Path], dest: Path, silence_ms: int) -> None:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        raise SystemExit("Concat needs soundfile and numpy: pip install soundfile") from e
    if not paths:
        return
    chunks: list[Any] = []
    sr = None
    for p in paths:
        data, file_sr = sf.read(str(p), always_2d=False)
        if sr is None:
            sr = file_sr
        elif file_sr != sr:
            raise ValueError(f"Sample rate mismatch: {p} ({file_sr}) vs {sr}")
        if data.ndim == 1:
            chunks.append(data)
        else:
            chunks.append(data.mean(axis=1))
        if silence_ms > 0 and sr:
            n = int(sr * (silence_ms / 1000.0))
            if n > 0:
                chunks.append(np.zeros(n, dtype=chunks[-1].dtype))
    if silence_ms > 0 and chunks:
        chunks.pop()
    merged = np.concatenate(chunks, axis=0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dest), merged, sr or 24000)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--roster", type=Path, required=True, help="characters.yaml or .json")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Coqui model id")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--character", help="Character id from roster (single-line mode)")
    p.add_argument("--text", help="Utterance for single-line mode")
    p.add_argument("--out", type=Path, help="Output WAV (single-line mode)")
    p.add_argument("--dialogue", type=Path, help="JSON with { lines: [{character, text}, ...] }")
    p.add_argument("--out-dir", type=Path, help="Directory for per-line WAVs (dialogue mode)")
    p.add_argument(
        "--concat-out",
        type=Path,
        help="Optional combined WAV for dialogue mode",
    )
    p.add_argument(
        "--line-silence-ms",
        type=int,
        default=350,
        help="Silence inserted between lines when using --concat-out",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    raw = load_roster(args.roster)
    _, roster = parse_roster(raw, args.roster)

    if args.device == "auto":
        try:
            import torch

            use_gpu = torch.cuda.is_available()
        except ImportError:
            use_gpu = False
    else:
        use_gpu = args.device == "cuda"

    TTS = _ensure_tts_class()
    tts = TTS(model_name=args.model, gpu=use_gpu)

    if args.dialogue:
        if not args.out_dir:
            raise SystemExit("Dialogue mode requires --out-dir")
        with args.dialogue.open(encoding="utf-8") as f:
            dlg = json.load(f)
        lines = dlg.get("lines")
        if not isinstance(lines, list):
            raise SystemExit("dialogue.json must contain a 'lines' array")
        written: list[Path] = []
        for i, row in enumerate(lines, start=1):
            if not isinstance(row, dict):
                continue
            cid = str(row.get("character") or "").strip()
            text = str(row.get("text") or "").strip()
            if not cid or not text:
                continue
            if cid not in roster:
                raise SystemExit(f"Unknown character in dialogue: {cid!r}")
            spec = roster[cid]
            fname = f"{i:03d}_{cid}.wav"
            out_path = args.out_dir / fname
            synthesize_to_file(
                tts,
                text,
                spec["reference_wavs"],
                spec["language"],
                out_path,
            )
            written.append(out_path)
            print(out_path)
        if args.concat_out and written:
            concat_wavs(written, args.concat_out, args.line_silence_ms)
            print(args.concat_out)
        return

    if not args.character or not args.text or not args.out:
        raise SystemExit("Single-line mode needs --character, --text, and --out")
    cid = args.character.strip()
    if cid not in roster:
        raise SystemExit(f"Unknown character: {cid!r}")
    spec = roster[cid]
    synthesize_to_file(
        tts,
        args.text,
        spec["reference_wavs"],
        spec["language"],
        args.out,
    )
    print(args.out.resolve())


if __name__ == "__main__":
    main()
