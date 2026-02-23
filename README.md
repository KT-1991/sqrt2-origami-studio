# Sqrt2 Origami Studio

Origami crease-pattern research project with:

- Python prototypes for tiling / crease generation / fold preview
- A client-only TypeScript + Vue web app (`webapp/`)

## Repository Layout

- `py/`: Python pipeline and experiments
- `webapp/`: static Vue app (runs fully on client side)
- `docs/`: migration notes and implementation plans

## Web App (Local)

```powershell
cd webapp
npm install
npm run dev
```

Build:

```powershell
npm run build
```

Typecheck:

```powershell
npm run typecheck:web
npm run typecheck:engine
```

## GitHub Pages Deployment

This repo includes a Pages workflow:

- `.github/workflows/pages.yml`

Setup once in GitHub:

1. Push repository to GitHub (`main` branch).
2. Open `Settings -> Pages`.
3. Set `Source` to `GitHub Actions`.
4. Push to `main` (or run workflow manually) to publish.

The Vite base path is auto-configured in CI using `GITHUB_REPOSITORY`,
so project pages (`https://<user>.github.io/<repo>/`) work without extra edits.

## License

License is currently not set. Add `LICENSE` before public release.
