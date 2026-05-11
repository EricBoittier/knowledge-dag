#!/usr/bin/env python3
"""
Build a DaVinci-compatible FCPXML timeline from a philosophy dialogue JSON + CSM turn WAVs.

Aligns each turn_*.wav duration with one stylized B-roll clip (round-robin from stylized_broll_pool)
and writes subtitle_segments from the same chunk order used by synthesize_dialogue_csm.py.

Example:
  python3 video-pipeline/scripts/philosophy_dialogue_to_timeline.py \\
    --dialogue-json video-pipeline/content/philosophy/01_simulacra.dialogue.json \\
    --turns-dir video-pipeline/content/philosophy/01_simulacra_turns \\
    --mix-wav video-pipeline/content/philosophy/01_simulacra.wav \\
    --out-manifest video-pipeline/content/philosophy/01_simulacra.manifest.json \\
    --out-overlay video-pipeline/content/philosophy/01_simulacra.overlay.json \\
    --out-fcpxml video-pipeline/content/philosophy/01_simulacra.fcpxml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _src_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "src"


def _load_timeline_builder():
    sys.path.insert(0, str(_src_dir()))
    from build_timeline_fcpxml import build_timeline  # noqa: E402

    return build_timeline


def _load_probe():
    sys.path.insert(0, str(_src_dir()))
    from media_probe import probe_media, validate_probe  # noqa: E402

    return probe_media, validate_probe


def sentence_split(text: str, *, prefer_nltk: bool) -> list[str]:
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


def split_into_word_chunks(text: str, max_words: int, *, prefer_nltk: bool) -> list[str]:
    chunks: list[str] = []
    for sent in sentence_split(text, prefer_nltk=prefer_nltk):
        words = sent.split()
        if not words:
            continue
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i : i + max_words]).strip())
    return [c for c in chunks if c]


def flatten_turn_chunks(
    turns: list[dict],
    *,
    sentence_only: bool,
    max_words: int,
    prefer_nltk: bool,
) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for turn_idx, turn in enumerate(turns):
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        sid = int(turn.get("speaker_id", turn_idx % 3))
        if sentence_only:
            chunks = sentence_split(text, prefer_nltk=prefer_nltk)
        else:
            chunks = split_into_word_chunks(text, max_words, prefer_nltk=prefer_nltk)
        for ch in chunks:
            out.append((sid, ch))
    return out


def sorted_turn_wavs(turns_dir: Path) -> list[Path]:
    wavs = sorted(turns_dir.glob("turn_*.wav"))
    if not wavs:
        raise FileNotFoundError(f"No turn_*.wav under {turns_dir}")
    return wavs


def resolve_stylized_broll_path(raw: Path) -> Path:
    """Resolve pool path; prefer .mov over .mp4 for the same stem (DaVinci / FCPXML)."""
    p = raw.expanduser().resolve()
    suf = p.suffix.lower()
    if suf == ".mp4":
        mov = p.with_suffix(".mov")
        if mov.exists():
            return mov
        if p.exists():
            return p
    elif suf == ".mov":
        mp4 = p.with_suffix(".mp4")
        if p.exists():
            return p
        if mp4.exists():
            return mp4
    else:
        if p.exists():
            return p
    raise FileNotFoundError(f"B-roll not found (tried .mov/.mp4 where applicable): {p}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dialogue-json", type=Path, required=True)
    p.add_argument("--turns-dir", type=Path, required=True, help="Folder with turn_000.wav … from CSM dialogue synth")
    p.add_argument("--mix-wav", type=Path, default=None, help="Final mixed dialogue WAV for timeline lane -2")
    p.add_argument("--out-manifest", type=Path, required=True)
    p.add_argument("--out-overlay", type=Path, default=None, help="JSON with subtitle_segments (recommended for titles)")
    p.add_argument("--out-fcpxml", type=Path, default=None)
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="video-pipeline project_config.json (default: beside this script)",
    )
    p.add_argument("--sentence-only", action="store_true", help="Match synthesize_dialogue_csm.py --sentence-only")
    p.add_argument("--max-words", type=int, default=5, help="Chunk size when not --sentence-only")
    p.add_argument("--prefer-nltk", action="store_true")
    p.add_argument(
        "--fcpxml-relative-media",
        action="store_true",
        help=(
            "Emit file:../../... paths from the FCPXML directory. "
            "Default is absolute file:///… (Resolve on Linux often ignores relative URIs and only searches Media Storage)."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    dialogue_path = args.dialogue_json.expanduser().resolve()
    turns_dir = args.turns_dir.expanduser().resolve()
    mix_wav = args.mix_wav.expanduser().resolve() if args.mix_wav else None

    with dialogue_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    turns = payload.get("dialogue_plan") if isinstance(payload.get("dialogue_plan"), list) else payload.get("turns", [])
    if not isinstance(turns, list) or not turns:
        raise SystemExit("dialogue-json must contain dialogue_plan[] or turns[]")

    pool = payload.get("stylized_broll_pool") or []
    pool_paths = [resolve_stylized_broll_path(Path(p)) for p in pool if str(p).strip()]
    if not pool_paths:
        raise SystemExit("dialogue-json has no stylized_broll_pool (non-empty list of video paths)")

    flat = flatten_turn_chunks(
        turns,
        sentence_only=args.sentence_only,
        max_words=max(1, args.max_words),
        prefer_nltk=args.prefer_nltk,
    )
    wavs = sorted_turn_wavs(turns_dir)
    if len(flat) != len(wavs):
        raise SystemExit(
            f"Chunk count mismatch: dialogue expands to {len(flat)} chunks but found {len(wavs)} "
            f"turn_*.wav in {turns_dir}. Regenerate audio with matching --sentence-only / --max-words, or adjust dialogue."
        )

    probe_media, validate_probe = _load_probe()
    characters = payload.get("characters") or {}

    entries: list[dict] = []
    subtitle_segments: list[dict] = []
    t = 0.0
    for i, ((sid, text), wav_path) in enumerate(zip(flat, wavs, strict=True)):
        pr = validate_probe(wav_path, probe_media(wav_path))
        d = max(0.05, float(pr.duration_seconds))
        vid = pool_paths[i % len(pool_paths)]
        vprobe = validate_probe(vid, probe_media(vid))
        if not vprobe.has_video:
            raise SystemExit(f"Not a video file or missing video stream: {vid}")
        vdur = max(0.05, float(vprobe.duration_seconds))
        if vdur + 1e-3 < d:
            raise SystemExit(
                f"B-roll shorter than dialogue chunk ({vdur:.3f}s < {d:.3f}s): {vid.name}. "
                "Use longer stylized clips or shorter synthesis chunks."
            )
        usable = d
        label = f"Philosophy b-roll {i + 1}"
        name = characters.get(str(sid), f"Speaker {sid}")
        cue_text = f"{name}: {text}"

        entries.append(
            {
                "source": str(vid),
                "normalized": str(vid),
                "source_label": vid.name,
                "duration_seconds": usable,
                "video_codec": vprobe.video_codec or "",
                "audio_codec": vprobe.audio_codec or "",
                "timeline": {
                    "enabled": True,
                    "label": label,
                    "in_seconds": 0.0,
                    "out_seconds": usable,
                },
                "errors": [],
            }
        )
        subtitle_segments.append({"text": cue_text, "start": t, "end": t + usable})
        t += usable

    manifest = {
        "input_dir": str(dialogue_path.parent),
        "output_dir": str(dialogue_path.parent),
        "entries": entries,
    }
    out_manifest = args.out_manifest.expanduser().resolve()
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(out_manifest)

    out_overlay = args.out_overlay
    if out_overlay:
        out_overlay = out_overlay.expanduser().resolve()
        out_overlay.parent.mkdir(parents=True, exist_ok=True)
        overlay = {"subtitle_segments": subtitle_segments, "dialogue_plan": turns}
        out_overlay.write_text(json.dumps(overlay, indent=2), encoding="utf-8")
        print(out_overlay)

    if args.out_fcpxml:
        cfg = args.config
        if cfg is None:
            cfg = Path(__file__).resolve().parent.parent / "project_config.json"
        else:
            cfg = cfg.expanduser().resolve()
        build_timeline = _load_timeline_builder()
        out_xml = args.out_fcpxml.expanduser().resolve()
        tl_over = (
            {"fcpxml_relative_media_src": True}
            if args.fcpxml_relative_media
            else None
        )
        build_timeline(
            cfg,
            out_manifest,
            out_xml,
            overlay_manifest_path=out_overlay,
            dialogue_audio_path=mix_wav if mix_wav and mix_wav.is_file() else None,
            timeline_overrides=tl_over,
        )
        print(out_xml)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
