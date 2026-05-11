# Script Development

This area maps the AI/Human script workflow that turns an idea, topic, or wiki concept into a project script and edit annotations.

## Current Code

- `../../ai-director-app/scripts/bootstrap_dag_from_concept.py`: creates `dag.project.json` from a freeform concept.
- `../../ai-director-app/packages/planner/src/gemini-script-cli.ts`: generates script text and edit annotations.
- `../../ai-director-app/packages/planner/src/gemini-expand-dag-cli.ts`: expands a DAG via Gemini.
- `../../ai-director-app/packages/core/src/cli/build-project.ts`: runs the numbered source-to-upload stages.
- `../../ai-director-app/projects/walrus-dfs/script.md`: example generated script artifact.
- `../../ai-director-app/projects/walrus-dfs/edit-annotations.json`: example edit annotation artifact.

## Common Commands

```bash
cd ai-director-app
cp .env.video.example .env.video
./scripts/build_project_env.sh
```

```bash
cd ai-director-app
npm run desktop
```

Open `http://localhost:4317` for the local browser shell.

## Human Review Points

- Review `dag.project.json` before running expensive media stages.
- Edit `script.md` for tone, pacing, and correctness.
- Edit `edit-annotations.json` to guide visual selection, captions, and timing.
- Re-run from the relevant stage with `--from-stage` and `--to-stage`.
