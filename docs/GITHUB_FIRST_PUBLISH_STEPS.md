# GitHub First Publish Steps

Run from:

```powershell
cd C:\Users\chiku\Desktop\origami\test05
```

## 1) Initialize git and first commit

```powershell
git init -b main
git add .
git commit -m "Initial public release: Sqrt2 Origami Studio"
```

If git user is not configured:

```powershell
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL@example.com"
git add .
git commit -m "Initial public release: Sqrt2 Origami Studio"
```

## 2) Create GitHub repository

Create an empty repo on GitHub web UI (no README, no .gitignore, no license),
for example:

- Repository name: `sqrt2-origami-studio`

Then connect local repo:

```powershell
git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git
git push -u origin main
```

## 3) Enable GitHub Pages (Actions source)

In GitHub repository:

1. Open `Settings -> Pages`
2. Set `Source` to `GitHub Actions`

## 4) Verify deployment

After push, workflow runs:

- `.github/workflows/pages.yml`

Check:

1. `Actions` tab: workflow `Deploy Webapp To GitHub Pages` is green
2. `Settings -> Pages`: deployed URL is shown
3. Open URL:
   - `https://<YOUR_USER>.github.io/<YOUR_REPO>/`

## 5) If deployment fails (common settings)

In repository settings:

1. `Settings -> Actions -> General`
2. `Workflow permissions` = `Read and write permissions`

