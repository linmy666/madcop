#!/usr/bin/env node
/**
 * dev:electron — one-command local dev launcher.
 *
 * Kills any stale vite / electron / python-backend processes, rebuilds
 * the frontend bundle + electron main, starts vite + Electron, and
 * tails the relevant logs. Equivalent to clicking the desktop shortcut
 * after a `git pull` + edit cycle, but with the LATEST code.
 *
 * Usage:  node scripts/dev-electron.mjs
 *         (or `npm run dev:electron` from the desktop/ dir)
 */
import { spawn, execSync, spawnSync } from "node:child_process";
import { existsSync, statSync, watch as fsWatch, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESKTOP = dirname(HERE);
const REPO = dirname(DESKTOP);
const PYTHON = join(REPO, "madcop");

// Ports the launcher's various pieces need. Override via env if needed.
const VITE_PORT = process.env.MADCOP_VITE_PORT ?? "1420";
const BACKEND_PORT = process.env.MADCOP_BACKEND_PORT ?? "8765";
const RENDERER_URL = `http://localhost:${VITE_PORT}`;

// PID/log handles
const procs = [];
const cleanup = () => {
  for (const p of procs) {
    try { p.kill("SIGTERM"); } catch { /* ignore */ }
  }
  // Also nuke anything on our ports that we didn't spawn — a previous
  // session of MadCop/Electron can survive a kill if it bound itself
  // to a different launcher.
  for (const port of [VITE_PORT, BACKEND_PORT]) {
    try {
      spawnSync("lsof", ["-nP", "-iTCP:" + port, "-sTCPTCP:LISTEN", "-t"], { encoding: "utf8" })
        .stdout.trim().split("\n").filter(Boolean).forEach((pid) => {
          try { process.kill(parseInt(pid, 10), "SIGTERM"); } catch { /* ignore */ }
        });
    } catch { /* ignore */ }
  }
};
process.on("SIGINT", () => { cleanup(); process.exit(130); });
process.on("SIGTERM", () => { cleanup(); process.exit(143); });

// Pretty step label
const step = (label) => console.log(`\x1b[36m▶ ${label}\x1b[0m`);
const ok   = (label) => console.log(`\x1b[32m✓ ${label}\x1b[0m`);
const warn = (label) => console.log(`\x1b[33m⚠ ${label}\x1b[0m`);
const fail = (label) => { console.log(`\x1b[31m✗ ${label}\x1b[0m"); cleanup(); process.exit(1); };

function run(cmd, args, { cwd, env, stdio = "inherit" } = {}) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, env: env ?? process.env, stdio });
    p.on("error", reject);
    p.on("exit", (code) => code === 0
      ? resolve()
      : reject(new Error(`${cmd} ${args.join(" ")} exited ${code}`)));
  });
}

function tryBun(...args) {
  if (existsSync("/Users/linruihan/.bun/bin/bun")) {
    return "/Users/linruihan/.bun/bin/bun";
  }
  try {
    execSync("command -v bun", { stdio: "ignore" });
    return "bun";
  } catch {
    return null;
  }
}

// 1. Kill stale processes on our ports. Done early so later steps
//    can bind without waiting for TIME_WAIT.
step(`Freeing ports ${VITE_PORT} (vite) + ${BACKEND_PORT} (backend)`);
cleanup();
await new Promise((r) => setTimeout(r, 500));
ok("ports free");

// 2. Rebuild the frontend bundle so the Electron main can load the
//    latest dist-vue/index.html. Skip if no source changes since the
//    last build (Vite's dist mtime check).
const distIndex = join(DESKTOP, "dist-vue", "index.html");
const needFrontend = () => {
  if (!existsSync(distIndex)) return true;
  const sources = [
    join(DESKTOP, "src"),
    join(DESKTOP, "vite.vue.dev.config.ts"),
  ];
  const distM = statSync(distIndex).mtimeMs;
  for (const root of sources) {
    if (!existsSync(root)) continue;
    try {
      const out = execSync(`find ${root} -type f -newer ${distIndex} -not -path '*/node_modules/*'`, { encoding: "utf8" });
      if (out.trim()) {
        warn(`frontend source changed after last build: ${out.trim().split("\n").length} files`);
        return true;
      }
    } catch { /* find may fail on weird trees — just rebuild */ return true; }
  }
  return false;
};
if (needFrontend()) {
  step("Building frontend bundle (vite)");
  await run("node", [
    "./node_modules/typescript/bin/tsc", "-b",
  ], { cwd: DESKTOP }).catch((e) => warn(`tsc reported errors (continuing): ${e.message}`));
  await run("node", ["./node_modules/vite/bin/vite.js", "build"], { cwd: DESKTOP });
  ok("frontend bundle built");
} else {
  ok("frontend bundle up to date");
}

// 3. Rebuild electron main + preload (dist-vue references it via the
//    .main.cjs entrypoint). Use bun if present, fall back to npx.
const electronDist = join(DESKTOP, "electron-dist", "main.cjs");
const bun = tryBun();
if (bun) {
  step("Building electron main + preload");
  try {
    await run(bun, ["run", "./scripts/prepare-node-pty.ts"], { cwd: DESKTOP });
    await run(bun, ["build", "./electron/main.ts", "--outfile", "./electron-dist/main.cjs",
                    "--target", "node", "--format", "cjs", "--external", "electron", "--external", "node-pty"], { cwd: DESKTOP });
    await run(bun, ["build", "./electron/preload.ts", "--outfile", "./electron-dist/preload.cjs",
                    "--target", "node", "--format", "cjs", "--external", "electron"], { cwd: DESKTOP });
    await run(bun, ["build", "./electron/preview-preload.ts", "--outfile", "./electron-dist/preview-preload.cjs",
                    "--target", "node", "--format", "cjs", "--external", "electron"], { cwd: DESKTOP });
    ok("electron main + preload built");
  } catch (e) {
    fail(`electron build failed: ${e.message}`);
  }
} else {
  warn("bun not found — assuming electron-dist already built");
}

// 4. Rebuild the Python preview-agent (so the sidecar's bundled server
//    code is current). This is the part that gets the new chatStore /
//    engine fixes into the Electron-bundled backend.
const previewAgent = join(DESKTOP, "src-tauri", "resources", "preview-agent.js");
const bunForBuild = tryBun();
if (bunForBuild) {
  step("Building python preview-agent bundle");
  try {
    await run(bunForBuild, ["run", "./scripts/build-preview-agent.ts"], { cwd: DESKTOP });
    ok("preview-agent built");
  } catch (e) {
    warn(`preview-agent build failed: ${e.message} (using existing)`);
  }
} else {
  warn("bun not found — assuming preview-agent.js is current");
}

// 5. Start vite dev server (serves the latest source for the in-app
//    browser at 1420 + can also load the dist build).
step(`Starting vite dev server on :${VITE_PORT}`);
const vite = spawn(
  "node",
  ["./node_modules/vite/bin/vite.js", "--port", VITE_PORT, "--host", "127.0.0.1"],
  { cwd: DESKTOP, env: {
      ...process.env,
      NO_PROXY: "localhost,127.0.0.1,::1",
      no_proxy: "localhost,127.0.0.1,::1",
    }, stdio: ["ignore", "pipe", "pipe"] },
);
procs.push(vite);
vite.stdout.on("data", (b) => process.stdout.write(`\x1b[90m[vite] ${b}\x1b[0m`));
vite.stderr.on("data", (b) => process.stderr.write(`\x1b[90m[vite] ${b}\x1b[0m`));

// Wait for vite to bind
await new Promise((resolve, reject) => {
  const deadline = Date.now() + 30_000;
  const probe = setInterval(async () => {
    try {
      const r = await fetch(RENDERER_URL);
      if (r.ok) { clearInterval(probe); resolve(); }
    } catch { /* not ready yet */ }
    if (Date.now() > deadline) { clearInterval(probe); reject(new Error("vite didn't start in 30s")); }
  }, 250);
});
ok(`vite ready at ${RENDERER_URL}`);

// 6. Start Electron pointing at the running vite renderer.
step("Launching Electron app");
const electron = spawn(
  "./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron",
  ["./electron-dist/main.cjs"],
  { cwd: DESKTOP, env: {
      ...process.env,
      ELECTRON_RENDERER_URL: RENDERER_URL,
      NO_PROXY: "localhost,127.0.0.1,::1",
      no_proxy: "localhost,127.0.0.1,::1",
    }, stdio: ["ignore", "inherit", "inherit"] },
);
procs.push(electron);
electron.on("exit", (code) => {
  console.log(`\nElectron exited with code ${code}`);
  cleanup();
  process.exit(code ?? 0);
});
ok("Electron launched (close the window or Ctrl-C here to stop)");

// 7. Foreground: keep the script alive until Electron exits. If the
//    user hits Ctrl-C we also exit (the cleanup hook kills children).
process.stdin.resume();
