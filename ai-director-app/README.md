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

## Crop Validation

`validate` stage checks crop-bearing segments for:

- processed styled media creation (`output/processed/*.styled.mov`)
- FCPXML asset mapping to processed media

Validation details are written to `output/crop-validation.json` and summarized in `output/import-report.md`.

## DaVinci Import

1. Import normalized/processed media first.
2. Import `timeline_davinci_resolve.fcpxml`.
3. Optionally import `subtitles.srt` as editable subtitle track.
