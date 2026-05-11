# Training

This domain groups model training, fine-tuning, datasets, and generated model artifacts.

The current training code is focused on speech:

- `../voice_tts/`: Sesame CSM-1B text-to-speech fine-tuning and synthesis with Unsloth.
- `../voice_ft/`: Whisper ASR fine-tuning with Unsloth and LoRA.

See `unsloth/` for the current map and artifact policy.
