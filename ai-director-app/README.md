# AI Director Desktop App

Canonical merged app for DAG-driven video creation (replaces `dag-video-editor` as the primary runtime surface).

## Unified Numbered Flow

1. `source`
2. `planner`
3. `discovery`
4. `select`
5. `normalize`
6. `annotations`
7. `subtitles`
8. `export`
9. `validate`
10. `render`
11. `upload`

## Quick Start

```bash
cd ai-director-app
npm install
npm run run:dry
```

Desktop shell:

```bash
npm run desktop
```

Open `http://localhost:4317`.

## Stage Control

```bash
npm run build
node ./dist/core/src/cli/build-project.js --project ./projects/walrus-dfs --from-stage source --to-stage validate --dry-run
```

## CLI env runner (concept -> graph -> script -> narration -> video)

Use the env-driven wrapper to run end-to-end with cheap voices by default.

```bash
cd ai-director-app
cp .env.video.example .env.video
# Edit .env.video (PROJECT_DIR, CONCEPT, stage range, etc.)
./scripts/build_project_env.sh
```

Notes:
- When `CONCEPT` is set, `scripts/bootstrap_dag_from_concept.py` generates `dag.project.json`.
- `CHEAP_VOICES=1` exports `VOICEOVER_ENGINE=espeak` automatically.
- Default stage range is `source -> render`.

Backward-compatible stage aliases are accepted during migration (`media` -> `normalize`, `subtitle` -> `subtitles`, `timeline` -> `export`).

## Canonical Project Artifacts

Default project root:

- `projects/walrus-dfs`

Core outputs:
- `projects/walrus-dfs/shot-plan.json`
- `projects/walrus-dfs/script.md`
- `projects/walrus-dfs/edit-annotations.json`
- `projects/walrus-dfs/candidates.json`
- `projects/walrus-dfs/selected-clips.json`
- `projects/walrus-dfs/media-manifest.json`
- `projects/walrus-dfs/subtitles.srt`
- `projects/walrus-dfs/output/timeline_davinci_resolve.fcpxml`
- `projects/walrus-dfs/output/import-report.md`
- `projects/walrus-dfs/output/crop-validation.json`

## Local B-roll analysis

`normalize` can run a local image-to-text pass on normalized media and persist ranked windows in
`media-manifest.json` (`broll_analysis`, `broll_windows`, `broll_top_window`, `broll_markers`).

Enable and tune with `config/pipeline.config.json`:

- `broll_analyzer.enabled`
- `broll_analyzer.model_name`
- `broll_analyzer.device`
- `broll_analyzer.sample_interval_sec`
- `broll_analyzer.window_duration_sec`
- `broll_analyzer.max_windows`
- `broll_analyzer.min_window_score`
- `timeline.use_broll_top_window` (use best window as timeline trim)

## Crop Validation

`validate` stage checks crop-bearing segments for:

- processed styled media creation (`output/processed/*.styled.mov`)
- FCPXML asset mapping to processed media

Validation details are written to `output/crop-validation.json` and summarized in `output/import-report.md`.

## DaVinci Import

1. Import normalized/processed media first.
2. Import `timeline_davinci_resolve.fcpxml`.
3. Optionally import `subtitles.srt` as editable subtitle track.
