# Legacy React frontend

The production renderer is **Vue 3** only (`desktop/src/vue/`, built to `dist-vue/`).

- Electron loads **only** `dist-vue/index.html` (no React fallback).
- React sources under `desktop/src/` (`*.tsx`, `src/api` used by old UI) remain for reference and gradual deletion.
- Do **not** import `desktop/src/api/*` from Vue — use `desktop/src/vue/api/*` (enforced by `scripts/check-vue-client-imports.ts`).
- React client default port is also 8765 as a safety net.

Planned: move remaining React tree to an archive branch and delete from `main` once no types are shared.