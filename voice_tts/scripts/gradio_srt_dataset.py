#!/usr/bin/env python3
"""Local Gradio UI for building metadata.csv + 24 kHz WAVs from video + SRT.

  pip install -r ../requirements-srt-dataset.txt
  python3 gradio_srt_dataset.py

Requires ffmpeg in PATH; yt-dlp in PATH when using YouTube URL or auto-subs.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import gradio as gr

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import build_dataset_from_video_srt as srt_build  # noqa: E402


def _uploaded_path(maybe) -> Path | None:
    if maybe is None:
        return None
    if isinstance(maybe, dict):
        path_key = maybe.get("path") or maybe.get("name")
        if path_key:
            p = Path(str(path_key))
            return p if p.is_file() else None
        return None
    if isinstance(maybe, (str, Path)):
        p = Path(maybe)
        return p if p.is_file() else None
    name = getattr(maybe, "name", None)
    if name:
        p = Path(str(name))
        return p if p.is_file() else None
    return None


def _run(
    youtube_url: str,
    video_file,
    srt_file,
    out_dir: str,
    fetch_auto_subs: bool,
    min_duration_sec: float,
    filter_sfx: bool,
    min_letters: float,
    time_shift_sec: float,
    pad_start_sec: float,
    pad_end_sec: float,
) -> str:
    youtube_url = (youtube_url or "").strip()
    out_path = Path(out_dir or "").expanduser().resolve()
    if not out_path.parts:
        return "Set an output directory."

    work_root = Path(tempfile.mkdtemp(prefix="srt_dataset_"))
    try:
        media = _uploaded_path(video_file)

        if youtube_url and media is None:
            tpl = work_root / "source.%(ext)s"
            media = srt_build.download_youtube_video(youtube_url, tpl)

        if media is None:
            return "Provide a video file or a YouTube URL to download."

        if fetch_auto_subs:
            if not youtube_url:
                return "Auto subtitles require a YouTube URL."
            srt = srt_build.fetch_youtube_auto_subs_srt(youtube_url, work_root)
        else:
            srt = _uploaded_path(srt_file)
            if srt is None:
                return "Upload an .srt file or enable “Fetch YouTube auto-subs”."

        out_path.mkdir(parents=True, exist_ok=True)
        summary = srt_build.build_dataset(
            media,
            srt,
            out_path,
            sample_rate=24_000,
            min_duration_sec=float(min_duration_sec),
            filter_sfx_cues=bool(filter_sfx),
            min_letters=max(0, int(min_letters)),
            time_shift_sec=float(time_shift_sec or 0.0),
            pad_start_sec=max(0.0, float(pad_start_sec or 0.0)),
            pad_end_sec=max(0.0, float(pad_end_sec or 0.0)),
        )
        lines = [
            f"clips_written: {summary['clips_written']}",
            f"cues_total: {summary['cues_total']}",
            f"skipped: {summary['skipped']}",
            f"output: {summary['out_dir']}",
            f"metadata.csv: {summary['metadata_csv']}",
        ]
        return "\n".join(lines)
    except Exception as ex:
        return f"Error: {ex}"
    finally:
        try:
            shutil.rmtree(work_root, ignore_errors=True)
        except OSError:
            pass


def main() -> None:
    with gr.Blocks(title="SRT → voice dataset") as demo:
        gr.Markdown(
            "## Video + SRT → `metadata.csv` + 24 kHz mono WAVs\n"
            "Output matches `voice_ft.common.load_local_audio_metadata_dir` / CSM prep."
        )
        youtube = gr.Textbox(label="YouTube URL (optional if you upload video)", lines=1)
        video = gr.File(
            label="Video / audio file",
            file_types=[".mp4", ".webm", ".mkv", ".mov", ".wav", ".m4a", ".flac", ".ogg"],
        )
        srt = gr.File(label="Subtitle .srt", file_types=[".srt"])
        fetch_auto = gr.Checkbox(label="Fetch YouTube auto-subs (needs URL; ignores SRT upload)")
        out_dir = gr.Textbox(label="Output directory", value=str(Path.cwd() / "srt_dataset_out"))
        min_dur = gr.Number(label="Min cue duration (seconds)", value=0.05, minimum=0)
        filter_sfx = gr.Checkbox(
            label="Skip / clean SFX cues ([Music], [ __ ], applause, etc.)",
            value=True,
        )
        min_letters = gr.Number(
            label="Minimum letters in cleaned text (per cue)",
            value=1,
            minimum=0,
            precision=0,
        )
        time_shift = gr.Number(
            label="Time shift (sec): add to every cue cut (positive = later in file)",
            value=0.0,
        )
        pad_start = gr.Number(
            label="Pad start (sec): extend each clip earlier",
            value=0.0,
            minimum=0,
        )
        pad_end = gr.Number(
            label="Pad end (sec): extend each clip later",
            value=0.0,
            minimum=0,
        )
        go = gr.Button("Build dataset", variant="primary")
        log = gr.Textbox(label="Result", lines=8)

        go.click(
            _run,
            inputs=[
                youtube,
                video,
                srt,
                out_dir,
                fetch_auto,
                min_dur,
                filter_sfx,
                min_letters,
                time_shift,
                pad_start,
                pad_end,
            ],
            outputs=[log],
        )

    demo.launch(server_name="127.0.0.1")


if __name__ == "__main__":
    main()
