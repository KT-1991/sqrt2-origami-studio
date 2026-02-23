UI Pattern Mock Lab

Purpose
- Compare visual directions without touching the production UI behavior.
- Use static/mock controls only; no engine-side behavior changes.

How to open
- Normal app:
  - `http://localhost:5173/`
- Mock pattern lab:
  - `http://localhost:5173/?mode=ui-mock`

What is included
- 10 style variants in one screen:
  - `Atelier`
  - `Draftboard`
  - `Rice Paper`
  - `Workbench (VSCode-like)`
  - `Workbench Midnight`
  - `Workbench Glass`
  - `Workbench Sand`
  - `Workbench CRT`
  - `Workbench Schematic`
  - `Workbench CAD Light`
- Layout and visual language experiments only.
- No interaction with worker/engine.

Files
- `webapp/ui/mock/DesignMockLab.vue`
- `webapp/ui/mock/design_mock_lab.css`
- `webapp/ui/main.ts` (query-param switch)
