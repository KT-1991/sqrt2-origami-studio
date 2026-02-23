# Project Layout

This repository now separates Python research code and Web app code.

## Top-level folders

- `py/`: Python implementations and legacy experiments.
- `webapp/`: TypeScript/WebWorker code and Vue UI for the client-side web app.
- `_tmp_out/`: temporary outputs and local test artifacts.

## Web app working directory

Run TypeScript checks and fixtures from `webapp/`.

Examples:

```powershell
cd webapp
npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json
npm exec --yes --package tsx -- tsx --eval "import { runCreasegenProfilesFixture } from './src/engine/creasegen_profiles_fixtures.ts'; runCreasegenProfilesFixture();"
```

Vue app files:

- `webapp/ui/main.ts`
- `webapp/ui/App.vue`
- `webapp/src/workers/origami_engine.worker.ts`
