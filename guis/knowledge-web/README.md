# Knowledge Web GUI

This maps the original knowledge DAG web application that still lives at the repository root.

## Current Code

- `../../src/server-main/index.ts`: Express server entrypoint.
- `../../src/server/create-app.ts`: Express app wiring.
- `../../src/client/`: React 16 client application.
- `../../src/flavormark/`: Markdown rendering stack.
- `../../webpack.config.ts`: Webpack client bundle configuration.
- `../../migrations/`: database migrations.

## Common Commands

```bash
npm install
cp development.sample.env development.env
cp client-config.sample.json client-config.json
npm run watch
WATCH=TRUE npm run webpack-dev
npm run migrate-up-to-latest
npm run start
```

Default local server port is `8228` unless overridden in `development.env`.
