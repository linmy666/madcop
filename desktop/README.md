# MadCop Agent Desktop

Electron desktop shell for **MadCop Agent**, a local-first AI agent with 4-layer memory, tool-use, and trace DAG.

## Architecture

- **Electron main process** (`electron/main.ts`) — bundles to `electron-dist/main.cjs` via `bun run build:electron`
- **Vite/React frontend** (`src/`, `index.html`) — bundles to `dist/` via `bun run build`
- **Backend** — standalone MadCop FastAPI on `http://127.0.0.1:8765` (NOT bundled in this app)

The Electron shell binds to the standalone FastAPI backend in the parent project
(`../madcop/server/`). It does **not** spawn its own sidecar.

## How it integrates with the parent MadCop project

The `madcop-agent-desktop` shell and the `madcop` FastAPI backend are tightly
integrated:

- Electron loads `dist/index.html` (a rebranded cc-haha React UI) and calls
  `http://127.0.0.1:8765/api/*` for all backend data
- All Skills, MCP, IM, and OAuth are handled by the parent MadCop backend
- Provider configuration, conversation history, and memory are persisted by
  MadCop's SQLite + JSON store (not by the Electron app)

This means **you must run the MadCop FastAPI backend first** before opening
the desktop app:

```bash
cd /Users/linruihan/PycharmProjects/madcop
python3 -m madcop.server
```

Then start the Electron shell:

```bash
cd /Users/linruihan/PycharmProjects/madcop/desktop
bun install                  # one-time
bun run build                # rebuild frontend
bun run build:electron       # rebuild Electron main
./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron ./electron-dist/main.cjs
```

## Development

```bash
# Terminal 1: FastAPI backend (must be running)
cd /Users/linruihan/PycharmProjects/madcop
python3 -m madcop.server

# Terminal 2: Vite dev server (HMR for React)
cd /Users/linruihan/PycharmProjects/madcop/desktop
bun run dev
```

## License

The Electron shell and React frontend are based on the open-source **cc-haha**
project (MIT licensed) and rebranded to MadCop Agent. All UI text, branding,
and assets have been replaced; the underlying React/Vite/Electron architecture
is preserved.

## Forked from

cc-haha — open source Claude Code-style desktop app.
