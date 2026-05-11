# AI Director GUI

This maps the local browser shell for the DAG-driven video workflow.

## Current Code

- `../../ai-director-app/apps/desktop/server.js`: local Node server and API wrapper.
- `../../ai-director-app/apps/desktop/ui.js`: browser UI logic.
- `../../ai-director-app/packages/core/src/cli/build-project.ts`: stage runner invoked by the UI.
- `../../ai-director-app/packages/planner/src/gemini-script-cli.ts`: script generation CLI invoked by the UI.
- `../../ai-director-app/packages/planner/src/gemini-expand-dag-cli.ts`: DAG expansion CLI invoked by the UI.

## Common Commands

```bash
cd ai-director-app
npm install
npm run build
npm run desktop
```

Open `http://localhost:4317`.

Use this GUI for project inspection, script planning, Gemini-assisted expansion, and running the pipeline stages from a browser surface.
