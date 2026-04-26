#!/usr/bin/env python3
"""Build CSM-ready audio dataset: video/audio + SRT → metadata.csv + 24 kHz mono WAVs.

Compatible with voice_ft.common.load_local_audio_metadata_dir (file_name, text).

Examples:
  python3 scripts/build_dataset_from_video_srt.py \\
    --media lecture.mp4 --srt lecture.srt --out ./data/my_voice

  python3 scripts/build_dataset_from_video_srt.py \\
    --youtube-url 'https://www.youtube.com/watch?v=...' --srt subs.srt --out ./out

  # Download video and auto-fetch YouTube subtitles (less reliable than a known SRT):
  python3 scripts/build_dataset_from_video_srt.py \\
    --youtube-url 'https://www.youtube.com/watch?v=...' --fetch-auto-subs --out ./out

  # If text/audio feel early or late, nudge timing (try ±0.05–0.15 s):
  python3 scripts/build_dataset_from_video_srt.py \\
    --media x.mp4 --srt x.srt --out ./out --time-shift-sec 0.08

  # Fix wrong YouTube/SRT captions using Whisper on each clip:
  pip install -r ../requirements-whisper-refine.txt
  python3 scripts/refine_dataset_text_whisper.py --data-dir ./out --backup
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SrtCue:
    start_sec: float
    end_sec: float
    text: str


def _ts_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    h_str, m_str, s_str = ts.split(":")
    h, m = int(h_str), int(m_str)
    s = float(s_str)
    return h * 3600 + m * 60 + s


_TIME_LINE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)

# Remove subtitle lines that are only sound effects / censors / musical notation.
_SFX_EXACT = frozenset(
    {
        "applause",
        "cheering",
        "laughter",
        "silence",
        "inaudible",
        "crosstalk",
        "beep",
        "bleep",
        "sigh",
        "sighs",
        "gasp",
        "gasps",
        "grunt",
        "mouthing",
        "no audio",
        "speaking indistinctly",
        "indistinct chatter",
        "crowd chattering",
        "laughs",
        "laughing",
        "chuckles",
        "chuckling",
    }
)


def _should_remove_bracket_inner(inner: str) -> bool:
    """True for [music], [ __ ], […], (applause), etc.; False for unknown tags like names."""
    t = inner.strip().lower()
    if not t:
        return True
    if re.fullmatch(r"[\s_.\u2026…▁‑–—]+", t):
        return True
    naked = re.sub(r"\s+", "", t)
    if re.fullmatch(r"[_\.\u2026…▁‑–—]+", naked):
        return True
    t_compact = re.sub(r"\s+", " ", t)
    if t_compact in _SFX_EXACT:
        return True
    if re.fullmatch(
        r"music(\s+(playing|continues|fades?|sting|stops))?|mouthing",
        t_compact,
    ):
        return True
    if "music" in t_compact and len(t_compact) < 28:
        return True
    return False


def _strip_sfx_brackets(text: str) -> str:
    """Remove [...] and (...) whose content looks like SFX / censor placeholders."""

    def sq(m: re.Match[str]) -> str:
        return " " if _should_remove_bracket_inner(m.group(1)) else m.group(0)

    def rnd(m: re.Match[str]) -> str:
        return " " if _should_remove_bracket_inner(m.group(1)) else m.group(0)

    out = re.sub(r"\[([^\]]*)\]", sq, text)
    out = re.sub(r"\(([^)]*)\)", rnd, out)
    return out


def cue_text_for_speech_training(
    raw: str,
    *,
    min_letters: int = 1,
) -> str | None:
    """Strip SFX/censor markers; return cleaned transcript or None to skip this cue."""
    text = _strip_srt_markup(raw)
    text = _strip_sfx_brackets(text)
    text = re.sub(r"[♪♫🎵🎶]+", " ", text)
    text = " ".join(text.split())
    if not text:
        return None
    n_letters = sum(1 for ch in text if ch.isalpha())
    if n_letters < min_letters:
        return None
    return text


def _strip_srt_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.split())


def parse_srt_content(raw: str) -> list[SrtCue]:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", raw.strip())
    cues: list[SrtCue] = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.split("\n")]
        lines = [ln for ln in lines if ln.strip() != ""]
        if not lines:
            continue
        time_idx: int | None = None
        for i, ln in enumerate(lines):
            if "-->" in ln:
                time_idx = i
                break
        if time_idx is None:
            continue
        m = _TIME_LINE.search(lines[time_idx])
        if not m:
            continue
        start = _ts_to_seconds(m.group(1))
        end = _ts_to_seconds(m.group(2))
        body = " ".join(lines[time_idx + 1 :])
        text = _strip_srt_markup(body)
        if end <= start or not text:
            continue
        cues.append(SrtCue(start_sec=start, end_sec=end, text=text))
    return cues


def parse_srt_path(path: Path) -> list[SrtCue]:
    return parse_srt_content(path.read_text(encoding="utf-8", errors="replace"))


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n{proc.stderr or proc.stdout}"
        )


def _which_or_raise(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name} not found in PATH")


def probe_media_duration_sec(path: Path) -> float | None:
    """Container duration in seconds, or None if unknown."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def extract_audio_segment_wav(
    media: Path,
    start_sec: float,
    end_sec: float,
    out_wav: Path,
    *,
    sample_rate: int = 24_000,
) -> None:
    """Mono PCM s16le WAV via ffmpeg ``atrim`` + ``aresample`` (avoids -ss/-to A/V sync quirks)."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.0, end_sec - start_sec)
    if duration <= 0:
        raise ValueError("Non-positive segment duration")
    # atrim uses decoded audio timeline; asetpts resets PTS; aresample hits target rate in one pass.
    filt = (
        f"atrim=start={start_sec:.6f}:end={end_sec:.6f},"
        "asetpts=PTS-STARTPTS,"
        f"aresample={sample_rate}"
    )
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(media),
        "-map",
        "0:a:0",
        "-af",
        filt,
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    _run(cmd)


def download_youtube_video(url: str, out_tpl: Path) -> Path:
    """Download best video+audio (<=1080p) with yt-dlp; return path to downloaded file."""
    _which_or_raise("yt-dlp")
    base = [
        "yt-dlp",
        "--no-playlist",
        "--socket-timeout",
        "30",
        "--retries",
        "4",
        "--fragment-retries",
        "4",
        "-o",
        str(out_tpl),
    ]
    attempts = [
        [*base, "--force-ipv4", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", url],
        [*base, "--force-ipv4", "-f", "b", url],
        [*base, "--force-ipv4", url],
    ]
    last = ""
    for cmd in attempts:
        try:
            _run(cmd)
            break
        except RuntimeError as ex:
            last = str(ex)
            continue
    else:
        raise RuntimeError(f"yt-dlp failed: {last[:500]}")
    parent = out_tpl.parent
    stem = out_tpl.stem
    matches = sorted(parent.glob(f"{stem}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError(f"No file written matching {out_tpl}")
    return matches[0]


def fetch_youtube_auto_subs_srt(url: str, work_dir: Path) -> Path:
    """Download auto/manual subs from YouTube as SRT; return path to one .srt file."""
    _which_or_raise("yt-dlp")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = work_dir / "subs.%(ext)s"
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-format",
        "srt",
        "--sub-langs",
        "en.*,en",
        "-o",
        str(out_tpl),
        url,
    ]
    _run(cmd)
    srts = sorted(work_dir.glob("*.srt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not srts:
        raise RuntimeError(
            "yt-dlp did not produce any .srt (try supplying --srt or check captions)."
        )
    return srts[0]


def build_dataset(
    media_path: Path,
    srt_path: Path,
    out_dir: Path,
    *,
    sample_rate: int = 24_000,
    min_duration_sec: float = 0.05,
    audio_subdir: str = "audio",
    filter_sfx_cues: bool = True,
    min_letters: int = 1,
    time_shift_sec: float = 0.0,
    pad_start_sec: float = 0.0,
    pad_end_sec: float = 0.0,
) -> dict:
    """Write ``out_dir/audio/*.wav`` and ``out_dir/metadata.csv``. Returns run summary.

    ``time_shift_sec``: added to every cue start/end before cutting (positive = later in file;
    tune if subs are consistently early/late vs audio). ``pad_*`` widen the window (clamped to
    file bounds).
    """
    _which_or_raise("ffmpeg")
    media_path = media_path.resolve()
    srt_path = srt_path.resolve()
    out_dir = out_dir.resolve()
    if not media_path.is_file():
        raise FileNotFoundError(media_path)
    if not srt_path.is_file():
        raise FileNotFoundError(srt_path)

    media_duration = probe_media_duration_sec(media_path)

    cues = parse_srt_path(srt_path)
    audio_root = out_dir / audio_subdir
    audio_root.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str]] = []
    skipped = 0
    written = 0
    for cue in cues:
        dur = cue.end_sec - cue.start_sec
        if dur < min_duration_sec:
            skipped += 1
            continue
        label = cue.text
        if filter_sfx_cues:
            cleaned = cue_text_for_speech_training(cue.text, min_letters=min_letters)
            if cleaned is None:
                skipped += 1
                continue
            label = cleaned
        t0 = cue.start_sec + time_shift_sec - pad_start_sec
        t1 = cue.end_sec + time_shift_sec + pad_end_sec
        t0 = max(0.0, t0)
        if media_duration is not None:
            t1 = min(t1, max(media_duration, 0.0))
        if t1 <= t0 or (t1 - t0) < min_duration_sec:
            skipped += 1
            continue
        written += 1
        rel = f"{audio_subdir}/{written:06d}.wav"
        dest = out_dir / rel
        try:
            extract_audio_segment_wav(
                media_path, t0, t1, dest, sample_rate=sample_rate
            )
        except RuntimeError:
            skipped += 1
            written -= 1
            continue
        rows.append((rel, label))

    meta = out_dir / "metadata.csv"
    with meta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file_name", "text"])
        w.writeheader()
        for fn, text in rows:
            w.writerow({"file_name": fn, "text": text})

    return {
        "out_dir": str(out_dir),
        "cues_total": len(cues),
        "clips_written": len(rows),
        "skipped": skipped,
        "metadata_csv": str(meta),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--media", type=Path, default=None, help="Video or audio file path")
    p.add_argument("--srt", type=Path, default=None, help="Subtitle .srt path")
    p.add_argument("--out", type=Path, required=True, help="Output dataset directory")
    p.add_argument("--youtube-url", type=str, default=None, help="Download media with yt-dlp")
    p.add_argument(
        "--fetch-auto-subs",
        action="store_true",
        help="With --youtube-url only: download YouTube captions as SRT (no --srt)",
    )
    p.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help="Temp dir for yt-dlp output (default: <out>/.yt_work)",
    )
    p.add_argument("--sample-rate", type=int, default=24_000)
    p.add_argument("--min-duration-sec", type=float, default=0.05)
    p.add_argument(
        "--no-filter-sfx",
        action="store_true",
        help="Keep [Music], [ __ ], etc. in labels (not recommended for speech training).",
    )
    p.add_argument(
        "--min-letters",
        type=int,
        default=1,
        help="Skip cues whose cleaned text has fewer than this many letters (default 1).",
    )
    p.add_argument(
        "--time-shift-sec",
        type=float,
        default=0.0,
        help="Add to every cue start/end before cutting (positive = shift window later in file).",
    )
    p.add_argument(
        "--pad-start-sec",
        type=float,
        default=0.0,
        help="Extend each clip earlier by this many seconds (after time shift).",
    )
    p.add_argument(
        "--pad-end-sec",
        type=float,
        default=0.0,
        help="Extend each clip later by this many seconds (after time shift).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if args.fetch_auto_subs and not args.youtube_url:
        raise SystemExit("--fetch-auto-subs requires --youtube-url")

    out_dir = args.out.expanduser().resolve()
    work = args.download_dir
    if work is None:
        work = out_dir / ".yt_work"
    work = work.expanduser().resolve()

    media = args.media
    srt = args.srt

    if args.youtube_url:
        if media is None:
            work.mkdir(parents=True, exist_ok=True)
            tpl = work / "source.%(ext)s"
            media = download_youtube_video(args.youtube_url, tpl)
        if args.fetch_auto_subs:
            if srt is not None:
                raise SystemExit("Use either --srt or --fetch-auto-subs, not both.")
            work.mkdir(parents=True, exist_ok=True)
            srt = fetch_youtube_auto_subs_srt(args.youtube_url, work)
        elif srt is None:
            raise SystemExit("--youtube-url requires --srt or --fetch-auto-subs")
    if media is None or srt is None:
        raise SystemExit("Provide --media and --srt, or --youtube-url with --srt/--fetch-auto-subs")

    summary = build_dataset(
        media,
        srt,
        out_dir,
        sample_rate=args.sample_rate,
        min_duration_sec=args.min_duration_sec,
        filter_sfx_cues=not args.no_filter_sfx,
        min_letters=max(0, args.min_letters),
        time_shift_sec=args.time_shift_sec,
        pad_start_sec=max(0.0, args.pad_start_sec),
        pad_end_sec=max(0.0, args.pad_end_sec),
    )
    print(
        f"Wrote {summary['clips_written']} clips "
        f"({summary['skipped']} skipped) to {summary['out_dir']}",
        flush=True,
    )
    print(f"metadata.csv: {summary['metadata_csv']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
