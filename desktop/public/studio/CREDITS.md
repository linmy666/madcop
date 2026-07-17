# Studio assets & third-party licensing notes

## MadCop brand (first-class)

- **Character**: MadCop mascot only (`mascot.png` via `MascotAvatar`).
  Recolor preserves near-white eye whites and near-black pupils
  (`mascotRecolor.ts`).
- **Rooms**: `room-studio.svg`, `room-study.svg`, `room-cabin.svg` —
  original MadCop vector scenes.
- **Pixel walk sheet** (`walk-sheet.png`): optional, **off by default**.

## Inspired by (code ideas only — not vendored binaries)

### XSafeClaw (`XSafeAI/XSafeClaw`)
- **Code license**: MIT (`LICENSE`, Copyright 2026 XSafeAI).
- **README** also notes contact for commercial enterprise arrangements;
  the OSI MIT text itself grants commercial use for the *Software*.
- **What we used**: reimplemented patterns only:
  - grid pathfinding ideas (`studioPathFinder.ts` ↔ their `PathFinder.js`)
  - status/timeline normalize (`agentEventNormalize.ts` ↔ `AgentJourney`)
  - roster status filters / activity console (Agent Town UX)
- **What we did NOT copy into this repo**:
  - `frontend/public/character_assets/*` (Adam/Alex etc.) — no per-asset
    license file in-tree; third-party pixel packs often require separate
    attribution; **MadCop face stays MadCop**.
  - PixiJS engine, maps, beams, portals, music packs.

### 摸鱼大厂 (user project)
- Owned by the MadCop author; usable as design reference.
- **Not vendored**: office JPEG / colleague sprites (product IP stays MadCop).

## Summary for commercial MadCop Agent

| Asset / idea              | OK for MadCop product?      |
|---------------------------|-----------------------------|
| XSafeClaw MIT code ideas  | Yes (reimplement)           |
| XSafeClaw character PNGs  | **No** (ambiguous upstream) |
| MadCop mascot + SVG rooms | Yes                         |
| 摸鱼大厂 layout ideas     | Yes                         |
| 摸鱼大厂 colleague faces  | No (product choice)         |
