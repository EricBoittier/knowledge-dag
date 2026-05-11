# Unsloth Training

This area maps the existing Unsloth-based voice training utilities.

## Text-To-Speech: Sesame CSM

Current code:

- `../../voice_tts/scripts/train_sesame_csm.py`: CSM LoRA training entrypoint.
- `../../voice_tts/scripts/synthesize_sesame_csm.py`: single-utterance synthesis.
- `../../voice_tts/scripts/synthesize_dialogue_csm.py`: multi-turn dialogue synthesis.
- `../../voice_tts/csm_dataset.py`: dataset construction and processor formatting.
- `../../voice_tts/csm_model_patches.py`: compatibility patches for CSM, Transformers, Unsloth, and PEFT.
- `../../voice_tts/scripts/build_dataset_from_video_srt.py`: build TTS datasets from video plus subtitles.
- `../../voice_tts/scripts/gradio_srt_dataset.py`: local Gradio UI for SRT dataset creation.

Common command:

```bash
cd voice_tts
TORCHDYNAMO_DISABLE=1 python3.12 scripts/train_sesame_csm.py \
  --dataset-dir /path/to/your/dataset \
  --max-steps 200 \
  --lora-dir sesame_csm_lora
```

## ASR: Whisper

Current code:

- `../../voice_ft/scripts/train.py`: Whisper LoRA training entrypoint.
- `../../voice_ft/scripts/transcribe.py`: Whisper inference with optional LoRA.
- `../../voice_ft/common.py`: shared model, dataset, collator, and metric helpers.
- `../../voice_ft/dataset-ui/`: static recording UI for `metadata.csv` plus `audio/` datasets.

Common command:

```bash
cd voice_ft
python scripts/train.py --dataset-dir /path/to/your/dataset --max-steps 60
```

## Dataset Contract

Both voice stacks use a simple local dataset shape:

```text
dataset/
  metadata.csv
  audio/
    clip_000001.wav
```

`metadata.csv` contains at least `file_name,text`.

## Artifact Policy

LoRA directories and trainer checkpoints currently exist in several places, including `voice_tts/sesame_csm_lora*`, `voice_ft/whisper_lora`, `voice_ft/outputs`, and `sesame_csm_lora`.

For now, do not move these artifacts automatically. Treat this area as the canonical documentation for where training code expects them. A later migration should centralize large model artifacts under a gitignored or Git LFS-backed `models/` or `training/artifacts/` tree and then update configs that reference them.
