#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
_KD = _ROOT.parent
if str(_KD) not in sys.path:
    sys.path.insert(0, str(_KD))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_csm_impl: Any = None


def _sesame_module():
    """Lazy-load synthesize_sesame_csm.py (sets up Unsloth / patches)."""
    global _csm_impl
    if _csm_impl is not None:
        return _csm_impl
    path = _SCRIPTS / "synthesize_sesame_csm.py"
    spec = importlib.util.spec_from_file_location("voice_tts_sesame_csm_impl", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load CSM module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _csm_impl = mod
    return mod


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def has_lora_weights(path: str) -> bool:
    p = Path(path)
    if not p.is_dir():
        return False
    return (p / "adapter_model.safetensors").exists() or (p / "adapter_model.bin").exists()


def sentence_split(text: str, prefer_nltk: bool) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if prefer_nltk:
        try:
            import nltk
            from nltk.tokenize import sent_tokenize

            try:
                nltk.data.find("tokenizers/punkt")
            except LookupError:
                nltk.download("punkt", quiet=True)
            sents = [s.strip() for s in sent_tokenize(cleaned) if s.strip()]
            if sents:
                return sents
        except Exception:
            pass
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def split_into_word_chunks(text: str, max_words: int, prefer_nltk: bool) -> List[str]:
    chunks: List[str] = []
    for sent in sentence_split(text, prefer_nltk=prefer_nltk):
        words = sent.split()
        if not words:
            continue
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i : i + max_words]).strip())
    return [c for c in chunks if c]


def build_turn_wavs(
    *,
    turns: List[Dict[str, Any]],
    out_dir: Path,
    model_name: str,
    max_words: int,
    prefer_nltk: bool,
    sentence_only: bool,
    max_new_tokens: int,
    default_lora_dir: Path | None,
    device: str | None,
    context_wav: Path | None,
    context_text: str | None,
    quiet: bool,
) -> List[Path]:
    import torch

    ses = _sesame_module()
    load_csm_for_inference = ses.load_csm_for_inference
    synthesize_csm_to_file = ses.synthesize_csm_to_file

    generated: List[Path] = []
    out_idx = 0
    model = None
    processor = None
    dev: str | None = None
    loaded_lora_key: str | None = None

    for turn_idx, turn in enumerate(turns):
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        speaker_id = int(turn.get("speaker_id", turn_idx % 3))
        checkpoint_dir = str(turn.get("checkpoint_dir", "")).strip()
        turn_lora = Path(checkpoint_dir) if checkpoint_dir and has_lora_weights(checkpoint_dir) else None
        effective_lora = turn_lora or default_lora_dir
        lora_key = str(effective_lora.resolve()) if effective_lora else ""

        if sentence_only:
            chunks = sentence_split(text, prefer_nltk=prefer_nltk)
        else:
            chunks = split_into_word_chunks(text, max_words=max_words, prefer_nltk=prefer_nltk)
        if not chunks:
            continue

        if model is None:
            if not quiet:
                print(f"Loading CSM once: {model_name} (lora={effective_lora or 'none'}) …", flush=True)
            model, processor, dev = load_csm_for_inference(
                model_name=model_name,
                lora_dir=effective_lora,
                device=device,
            )
            loaded_lora_key = lora_key
        elif lora_key != loaded_lora_key:
            if not quiet:
                print("LoRA path changed — reloading CSM …", flush=True)
            del model
            model = None
            processor = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            model, processor, dev = load_csm_for_inference(
                model_name=model_name,
                lora_dir=effective_lora,
                device=device,
            )
            loaded_lora_key = lora_key

        assert model is not None and processor is not None and dev is not None

        for chunk in chunks:
            out_path = out_dir / f"turn_{out_idx:03d}.wav"
            out_idx += 1
            synthesize_csm_to_file(
                model=model,
                processor=processor,
                device=dev,
                text=chunk,
                speaker_id=speaker_id,
                out=out_path,
                max_new_tokens=max_new_tokens,
                context_wav=context_wav,
                context_text=context_text,
            )
            generated.append(out_path)

    return generated


def concat_wavs(wavs: List[Path], output: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but not found in PATH")
    concat_file = output.with_suffix(".concat.txt")
    lines = [f"file '{w.resolve()}'" for w in wavs]
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output),
            ]
        )
    finally:
        concat_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize multi-character dialogue using CSM checkpoints")
    parser.add_argument("--dialogue-json", required=True, help="JSON file with dialogue_plan or turns[]")
    parser.add_argument("--out", required=True, help="Final concatenated wav output")
    parser.add_argument("--work-dir", default="", help="Optional temp output folder for turn wavs")
    parser.add_argument("--model-name", default="unsloth/csm-1b")
    parser.add_argument("--lora-dir", type=Path, default=None, help="Default LoRA when a turn omits checkpoint_dir")
    parser.add_argument("--device", default=None, help="cuda / cpu (default: auto)")
    parser.add_argument("--context-wav", type=Path, default=None, help="Optional 24 kHz context for every chunk")
    parser.add_argument("--context-text", type=str, default=None, help="Required if --context-wav is set")
    parser.add_argument("--max-words", type=int, default=5, help="Max words per synthesis chunk (without --sentence-only)")
    parser.add_argument("--prefer-nltk", action="store_true", help="Use NLTK sentence tokenization when available")
    parser.add_argument("--sentence-only", action="store_true", help="Generate one clip per sentence")
    parser.add_argument("--max-new-tokens", type=int, default=96, help="Fast-path generation length cap")
    parser.add_argument("--quiet", action="store_true", help="Less console output")
    args = parser.parse_args()

    if args.context_wav is not None:
        cw = Path(args.context_wav).expanduser().resolve()
        if not cw.is_file():
            raise RuntimeError(f"Missing --context-wav: {cw}")
        args.context_wav = cw
        if not (args.context_text or "").strip():
            raise RuntimeError("--context-text is required when using --context-wav")

    payload = load_json(Path(args.dialogue_json).resolve())
    turns = payload.get("dialogue_plan") if isinstance(payload.get("dialogue_plan"), list) else payload.get("turns", [])
    if not isinstance(turns, list) or not turns:
        raise RuntimeError("dialogue-json must include dialogue_plan[] or turns[]")
    output = Path(args.out).resolve()
    work_dir = Path(args.work_dir).resolve() if args.work_dir else output.parent / f"{output.stem}_turns"
    work_dir.mkdir(parents=True, exist_ok=True)

    default_lora = Path(args.lora_dir).expanduser().resolve() if args.lora_dir else None

    wavs = build_turn_wavs(
        turns=turns,
        out_dir=work_dir,
        model_name=args.model_name,
        max_words=max(1, args.max_words),
        prefer_nltk=args.prefer_nltk,
        sentence_only=args.sentence_only,
        max_new_tokens=max(32, args.max_new_tokens),
        default_lora_dir=default_lora,
        device=args.device,
        context_wav=args.context_wav,
        context_text=args.context_text,
        quiet=args.quiet,
    )
    if not wavs:
        raise RuntimeError("No dialogue turns were synthesized")
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_wavs(wavs, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
