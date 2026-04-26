# `voice_tts`

## Sesame CSM-1B (Unsloth TTS)

Fine-tune and run **[Sesame CSM-1B](https://huggingface.co/sesame/csm-1b)** with [Unsloth](https://unsloth.ai/docs/basics/text-to-speech-tts-fine-tuning), using the same **`metadata.csv` + `audio/`** layout as [`voice_ft/dataset-ui`](../voice_ft/dataset-ui) (audio is loaded at **24 kHz** for CSM).

Reference notebook: [Sesame CSM (1B) TTS](https://github.com/unslothai/notebooks/blob/main/nb/Sesame_CSM_(1B)-TTS.ipynb).

**Train** (from repo root or `voice_tts/`; use the same Python env as Unsloth, e.g. `python3.12`). Training uses `transformers.AutoProcessor` for the dataset (the object returned second from `FastModel.from_pretrained` is not a full CSM processor).

```bash
cd voice_tts
TORCHDYNAMO_DISABLE=1 python3.12 scripts/train_sesame_csm.py \
  --dataset-dir /path/to/your/dataset \
  --max-steps 200 \
  --lora-dir sesame_csm_lora
```

Checkpoints (optional): `--save-steps 100` writes `outputs_csm/checkpoint-*` (use `--output-dir` to change). Resume with `--resume outputs_csm/checkpoint-500` (same CLI flags / data as before; keeps optimizer and step counter). `--save-total-limit` caps how many checkpoints are kept (default 5).

**Synthesize** (requires **`soundfile`**: `pip install soundfile`, also listed in [`requirements-csm-pins.txt`](requirements-csm-pins.txt)):

```bash
TORCHDYNAMO_DISABLE=1 python3.12 scripts/synthesize_sesame_csm.py \
  --lora-dir sesame_csm_lora \
  --text "Your line here." \
  --out out.wav
```

For more stable **voice/style**, pass a **24 kHz** reference clip and its exact transcript ([Unsloth docs](https://unsloth.ai/docs/basics/text-to-speech-tts-fine-tuning)):

```bash
python3.12 scripts/synthesize_sesame_csm.py \
  --lora-dir sesame_csm_lora \
  --context-wav ref_24k.wav \
  --context-text "Words spoken in ref_24k.wav" \
  --text "New sentence in the same voice." \
  --out out.wav
```

Re-export clips at 24 kHz if your WAVs are 16 kHz-only, or resample once (e.g. `sox in.wav -r 24000 out.wav`).

## Dataset from video + subtitles (YouTube / SRT)

Build a **CSM-ready** folder (`metadata.csv` + mono **24 kHz** WAVs under `audio/`) from a video file and an `.srt`, optionally downloading media with **yt-dlp**. The layout matches `voice_ft.common.load_local_audio_metadata_dir` and `--dataset-dir` for CSM training.

**Requirements:** `ffmpeg` in `PATH`; for YouTube URLs, `yt-dlp` in `PATH`.

### 1. Build clips from SRT

Script: [`scripts/build_dataset_from_video_srt.py`](scripts/build_dataset_from_video_srt.py)

```bash
cd voice_tts

# Local video + subtitle file
python3 scripts/build_dataset_from_video_srt.py \
  --media /path/to/video.mp4 \
  --srt /path/to/subs.srt \
  --out /path/to/dataset_out

# YouTube URL + your own SRT (timestamps must match the downloaded file)
python3 scripts/build_dataset_from_video_srt.py \
  --youtube-url 'https://www.youtube.com/watch?v=...' \
  --srt ./subs.srt \
  --out ./dataset_out

# YouTube + auto-downloaded captions (often lower quality than a hand-checked SRT)
python3 scripts/build_dataset_from_video_srt.py \
  --youtube-url 'https://www.youtube.com/watch?v=...' \
  --fetch-auto-subs \
  --out ./dataset_out
```

**Behavior notes:**

- Each subtitle cue becomes one row: `audio/000001.wav`, … and a line in `metadata.csv` (`file_name`, `text`).
- **SFX / censor cleanup (default on):** cues like `[Music]`, `[ __ ]`, and similar are skipped or stripped so labels are more speech-like. Use `--no-filter-sfx` for raw subtitle text.
- **Alignment:** audio is trimmed with ffmpeg **`atrim`** on the first audio stream. If clips sound consistently early or late vs. the text, tune **`--time-shift-sec`** (positive = shift the cut window later in the file). **`--pad-start-sec`** / **`--pad-end-sec`** widen each window (clamped to file duration).
- **Whisper refine (below)** is the recommended way to fix **wrong caption text** while keeping your cuts.

Useful flags: `--min-duration-sec`, `--min-letters`, `--sample-rate` (default 24000), `--download-dir` for yt-dlp temp files.

### 2. Refine labels with Whisper (optional, recommended for YouTube)

Auto and platform subtitles are often misheard or mis-timed at the **word** level. After the WAVs exist, re-transcribe **each clip** with **faster-whisper** and overwrite `text` in `metadata.csv`.

Install: [`requirements-whisper-refine.txt`](requirements-whisper-refine.txt)

```bash
pip install -r voice_tts/requirements-whisper-refine.txt
python3 voice_tts/scripts/refine_dataset_text_whisper.py \
  --data-dir /path/to/dataset_out \
  --model base \
  --backup
```

- **`--backup`** saves `metadata.csv.bak` before overwriting.
- **`--write other.csv`** writes a new CSV and leaves the original unchanged.
- **`--model`:** `tiny` … `large-v3` (quality vs. speed/VRAM).
- **`--device`** `cuda` / `cpu` / `auto`; **`--compute-type`** e.g. `float16`, `int8` (see faster-whisper docs).
- **`--language en`** or **`auto`** for detection.
- **`--vad-filter`** can help on long/noisy sources; for **short clips** it may drop audio—usually leave it off.
- If Whisper returns empty text, the **old caption is kept** unless you pass **`--no-fallback`**.

### 3. Local UI (Gradio)

Optional browser UI for the SRT → dataset step only (not Whisper refine):

```bash
pip install -r voice_tts/requirements-srt-dataset.txt
python3 voice_tts/scripts/gradio_srt_dataset.py
```

Opens a local app (default `127.0.0.1`) for URL / file upload, output directory, SFX filtering, and timing nudges.

### 4. Train CSM on the folder

Point **`--dataset-dir`** at the directory that contains **`metadata.csv`** and **`audio/`** (after any Whisper refine):

```bash
TORCHDYNAMO_DISABLE=1 python3 scripts/train_sesame_csm.py \
  --dataset-dir /path/to/dataset_out \
  --max-steps 200 \
  --lora-dir sesame_csm_lora
```

**Legal / practical:** respect YouTube terms, copyright, and consent when downloading or training on source material.

## Reproducibility and backups

**Pinned stack (one machine where CSM training ran end-to-end):**

| Component   | Version   |
|------------|-----------|
| Python     | 3.14.3    |
| torch      | 2.10.0    |
| transformers | 5.5.0  |
| peft       | 0.19.1    |
| datasets   | 4.3.0     |
| accelerate | 1.13.0    |
| dill       | 0.4.0     |
| unsloth    | 2026.4.8  |
| unsloth_zoo | 2026.4.9 |
| soundfile  | 0.13.1    |

Tighter pins are in [`requirements-csm-pins.txt`](requirements-csm-pins.txt). Install Unsloth per their docs first, then use that file only when you need to match this stack.

**Back up artifacts you care about:**

- **LoRA + processor:** the directory you pass to `--lora-dir` (default `sesame_csm_lora/`), e.g. `tar -czvf sesame_csm_lora_backup.tgz sesame_csm_lora`.
- **Dataset:** the `--dataset-dir` tree (`metadata.csv`, `audio/`, etc.), same idea with `tar` or `rsync` to another disk or repo.

Keeping the **same model id** (`unsloth/csm-1b`), **tokenizer/processor files** next to the LoRA, and **these versions** (or noting drift) makes checkpoints much easier to reload later.

## Coqui XTTS (reference cloning, no Unsloth)

[`scripts/synthesize.py`](scripts/synthesize.py) + [`requirements-tts.txt`](requirements-tts.txt) — character roster and **XTTS v2** zero-shot cloning (separate install).
