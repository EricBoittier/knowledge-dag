# DAG Video Editor

`../dag-video-editor/` is deprecated.

Use `../ai-director-app/` for new video work. It is the canonical DAG-driven video app and owns the current numbered flow:

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

Keep `dag-video-editor/` only for old project compatibility or reference while migrating any remaining commands.

Useful replacement entrypoints:

```bash
cd ai-director-app
npm run run:dry
npm run desktop
```

For the repo-wide map, see `../REPO_MAP.md`.
