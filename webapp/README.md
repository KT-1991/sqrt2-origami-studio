# Sqrt2 Origami Studio (Webapp)

Client-only TypeScript + Vue app.

## Setup

```powershell
cd webapp
npm install
```

## Development

```powershell
npm run dev
```

Open the shown local URL.

Main workflow in UI:

1. Use `Run / Global / Points & Edges / Generation` tabs on the left panel.
2. Place or edit points on paper canvas (snapped to `(a+b√2)/2^k` lattice).
3. Run tiling / crease generation / fold preview.
4. Inspect output in `Crease Pattern View` and `Folded Preview`.

Mock style lab:

- Open with `?mode=ui-mock`
- Example: `http://localhost:5173/?mode=ui-mock`

## Build

```powershell
npm run build
```

## Typecheck

```powershell
npm run typecheck:engine
npm run typecheck:web
```

## GitHub Pages

Pages deployment is handled by repository workflow at:

- `.github/workflows/pages.yml`

Vite `base` is auto-set during GitHub Actions build using repository name.

## Notes

- Engine/runtime code: `src/`
- Vue UI entry: `ui/main.ts`
- Worker: `src/workers/origami_engine.worker.ts`
