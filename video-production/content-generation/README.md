# Content Generation

This area maps the AI-assisted content generation pieces used by the video pipeline: scripts, b-roll analysis, generated visuals, style transfer, narration, and upload steps.

## Current Code

- `../../ai-director-app/packages/core/src/cli/build-project.ts`: canonical numbered DAG stage runner.
- `../../ai-director-app/packages/pipeline/src-py/generate_voiceover.py`: voiceover generation bridge.
- `../../ai-director-app/packages/pipeline/src-py/broll_analyzer.py`: local b-roll analysis in the AI Director pipeline.
- `../../ai-director-app/packages/pipeline/src-py/download_normalize.py`: download and normalization helper.
- `../../ai-director-app/scripts/wiki_to_video_project.py`: Wikipedia/Commons image scraper that creates an AI Director project.
- `../../video-pipeline/src/broll_analyzer.py`: local visual captioning for b-roll windows.
- `../../video-pipeline/src/gemini_broll_evaluator.py`: Gemini-assisted b-roll fit scoring.
- `../../video-pipeline/scripts/style_transfer_video.py`: frame-based style transfer.
- `../../video-pipeline/scripts/z_image_frame_cli.py`: Z-Image frame generation CLI.
- `../../video-pipeline/scripts/flux2_klein_4b_cli.py`: FLUX.2 Klein frame generation CLI.

## Common Commands

```bash
cd ai-director-app
npm run build
node ./dist/core/src/cli/build-project.js --project ./projects/walrus-dfs --dry-run
```

Create a still-image timeline from a Wikipedia page:

```bash
cd ai-director-app
python3 scripts/wiki_to_video_project.py --title Penguin --project-dir ./projects/penguins-wiki --force
npm run build
node ./dist/core/src/cli/build-project.js --project ./projects/penguins-wiki --from-stage export --to-stage export --dry-run
```

```bash
cd video-pipeline
python3 src/run_pipeline.py --config ./project_config.json --showcase --with-overlays
```

Voice synthesis and model training are documented in `../../training/unsloth/README.md`.
