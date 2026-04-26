# Whisper fine-tuning (`voice_ft`)

English-only Whisper (default `openai/whisper-tiny.en`) with Unsloth + LoRA. Training entrypoint: [`scripts/train.py`](scripts/train.py). Shared helpers: [`common.py`](common.py).

## Dataset UI (custom JS)

Static app under [`dataset-ui/`](dataset-ui): build a **phrase list** (one line per utterance), use each row’s **Rec** / **Stop** to capture that phrase, then export **16 kHz mono PCM WAV** plus **`metadata.csv`** (`file_name`, `text`) for local training.

- **Add phrase** — new row; edit the line as the ground-truth transcript.
- **Load common phrases** — inserts a built-in list of **Harvard-style** English sentences (classic speech-test lines with broad phonetic coverage); good starter set for voice / ASR adaptation.
- **Load from text** — paste many lines into the box (one phrase per line) and replace the list.
- **Rec** on a row starts the mic for that phrase only; **Stop** ends and attaches the WAV to that row. Finish one take before starting another.

Serve over **http://localhost** (or HTTPS) so microphone and, in Chromium, **Save to folder…** work. Opening `index.html` as a `file://` URL often blocks these APIs.

```bash
cd dataset-ui
python3 -m http.server 8765
```

Then open `http://localhost:8765`.

- **Save to folder…** — writes `audio/clip_XXXXXX.wav` and merges **`metadata.csv`** (File System Access API; Chromium-style browsers).
- **Download ZIP** — same layout inside the archive if folder pick is unavailable (Firefox/Safari).

Only rows with **both** non-empty text and a recording are exported. Rows already saved in this session are skipped on the next folder save until you re-record or clear the saved path (editing text clears the recording).

## Train on a local dataset

Point training at the dataset **root** (the directory that contains `metadata.csv` and the `audio/` folder):

```bash
cd voice_ft
python scripts/train.py --dataset-dir /path/to/your/dataset --max-steps 60
```

Hub datasets still work when **`--dataset-dir` is omitted** (default `--dataset`).

## Layout

```text
your_dataset/
  metadata.csv    # header: file_name,text
  audio/
    clip_000001.wav
    ...
```

## Dependencies

Training follows the [Unsloth Whisper notebook](https://colab.research.google.com/github/unslothai/notebooks/blob/main/nb/Whisper.ipynb) stack (Unsloth, `transformers`, `datasets`, `evaluate`, etc.). Install those in your environment before running `scripts/train.py`.
