/**
 * Fail if any file under desktop/src/vue imports the React-era API client
 * (desktop/src/api/*) which defaults to port 3456 instead of 8765.
 *
 * Usage: bun run scripts/check-vue-client-imports.ts
 * Exit 1 on violation.
 */
import { readdir, readFile, stat } from 'node:fs/promises'
import path from 'node:path'

const __dirname = path.dirname(new URL(import.meta.url).pathname)
const vueRoot = path.resolve(__dirname, '../src/vue')

// Any import that escapes vue/ into src/api is banned.
const BANNED = [
  /from\s+['"](?:\.\.\/)+api\//,           // ../../../api/ or ../../api/ climbing past vue
  /from\s+['"]@?\/?src\/api\//,
  /from\s+['"]\.\.\/\.\.\/\.\.\/api\//,    // explicit 3-level climb from components/*
]

// Allowed: from '../api/client' when file is under vue/ (that's vue/api)
// Ban only when the resolved path would leave vue/.

async function walk(dir: string, out: string[] = []): Promise<string[]> {
  const entries = await readdir(dir)
  for (const name of entries) {
    if (name === 'node_modules' || name === 'dist') continue
    const full = path.join(dir, name)
    const st = await stat(full)
    if (st.isDirectory()) await walk(full, out)
    else if (/\.(ts|tsx|vue|js|mjs)$/.test(name)) out.push(full)
  }
  return out
}

function climbsOutOfVue(file: string, specifier: string): boolean {
  if (!specifier.startsWith('.')) return false
  if (!specifier.includes('/api/') && !specifier.endsWith('/api') && !/\/api['"]?$/.test(specifier)) {
    // Only care about api client paths
    if (!/api\/client|api\/settings|api\/sessions|api\/search|api\/providers/.test(specifier)) {
      return false
    }
  }
  const dir = path.dirname(file)
  const resolved = path.resolve(dir, specifier)
  // If resolved path is under desktop/src/api (React), ban it
  const reactApi = path.resolve(vueRoot, '../../src/api')
  // normalize: vue is desktop/src/vue, so ../api from vue is vue/api; ../../api is src/api
  if (resolved.startsWith(path.resolve(vueRoot, '../api'))) {
    // desktop/src/api — React client
    return true
  }
  // Also ban if relative depth would leave vue for api/
  const rel = path.relative(vueRoot, resolved)
  if (rel.startsWith('..') && rel.includes(`${path.sep}api`)) return true
  return false
}

const IMPORT_RE = /(?:from|import)\s+['"]([^'"]+)['"]/g

async function main() {
  const files = await walk(vueRoot)
  const violations: Array<{ file: string; line: number; spec: string }> = []

  for (const file of files) {
    const text = await readFile(file, 'utf8')
    const lines = text.split('\n')
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      IMPORT_RE.lastIndex = 0
      let m: RegExpExecArray | null
      while ((m = IMPORT_RE.exec(line)) !== null) {
        const spec = m[1]
        if (climbsOutOfVue(file, spec) || BANNED.some((re) => re.test(line) && line.includes('api/'))) {
          // Double-check: vue/api is OK
          const dir = path.dirname(file)
          const resolved = path.resolve(dir, spec)
          if (resolved.includes(`${path.sep}vue${path.sep}api${path.sep}`) || resolved.endsWith(`${path.sep}vue${path.sep}api`)) {
            continue
          }
          if (resolved.includes(`${path.sep}src${path.sep}api${path.sep}`) || /[/\\]src[/\\]api$/.test(resolved)) {
            violations.push({ file: path.relative(vueRoot, file), line: i + 1, spec })
          }
        }
      }
    }
  }

  if (violations.length === 0) {
    console.log(`OK: scanned ${files.length} Vue files — no React api/client imports`)
    process.exit(0)
  }

  console.error(`FAIL: ${violations.length} Vue file(s) import React src/api (port 3456):`)
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}  ${v.spec}`)
  }
  process.exit(1)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
