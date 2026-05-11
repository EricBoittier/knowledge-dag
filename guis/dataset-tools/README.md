# Dataset Tools GUIs

This maps the small human-in-the-loop tools used to capture or prepare voice datasets.

## Current UIs

- `../../voice_ft/dataset-ui/`: static browser recorder for phrase-based ASR datasets.
- `../../voice_tts/scripts/gradio_srt_dataset.py`: Gradio UI for building CSM-ready datasets from video and SRT files.

## Static Recording UI

```bash
cd voice_ft/dataset-ui
python3 -m http.server 8765
```

Open `http://localhost:8765`.

## Gradio SRT Dataset UI

```bash
pip install -r voice_tts/requirements-srt-dataset.txt
python3 voice_tts/scripts/gradio_srt_dataset.py
```

Use these tools to create folders with `metadata.csv` plus `audio/`, then train with the commands documented in `../../training/unsloth/README.md`.
