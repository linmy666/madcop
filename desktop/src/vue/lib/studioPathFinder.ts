/**
 * Lightweight walk-grid pathfinder for MadCop studio.
 * Inspired by XSafeClaw agent_town PathFinder (MIT) — reimplemented, no copy of their assets.
 *
 * Grid: 0 = walkable, 1 = blocked. Coordinates are tile indices.
 */

export type Tile = { x: number; y: number }

export function buildDefaultStudioGrid(
  cols = 24,
  rows = 14,
): number[][] {
  // Floor is walkable; block top wall band and side walls lightly
  const g: number[][] = []
  for (let y = 0; y < rows; y++) {
    const row: number[] = []
    for (let x = 0; x < cols; x++) {
      let cell = 0
      if (y < 2) cell = 1 // wall / window band
      if (x === 0 || x === cols - 1) cell = 1
      if (y === rows - 1) cell = 0 // door row open
      row.push(cell)
    }
    g.push(row)
  }
  // Clear door opening bottom-center
  const mid = Math.floor(cols / 2)
  for (let x = mid - 2; x <= mid + 2; x++) {
    if (g[rows - 1]) g[rows - 1][x] = 0
    if (g[rows - 2]) g[rows - 2][x] = 0
  }
  return g
}

/** A* / BFS shortest path on grid. */
export function findPath(
  grid: number[][],
  from: Tile,
  to: Tile,
): Tile[] {
  const rows = grid.length
  const cols = grid[0]?.length || 0
  const key = (t: Tile) => `${t.x},${t.y}`
  const inBounds = (t: Tile) =>
    t.x >= 0 && t.y >= 0 && t.x < cols && t.y < rows && grid[t.y][t.x] === 0

  if (!inBounds(from) || !inBounds(to)) {
    return [to]
  }
  if (from.x === to.x && from.y === to.y) return [to]

  const q: Tile[] = [from]
  const prev = new Map<string, string | null>()
  prev.set(key(from), null)
  const dirs = [
    { x: 1, y: 0 },
    { x: -1, y: 0 },
    { x: 0, y: 1 },
    { x: 0, y: -1 },
  ]

  while (q.length) {
    const cur = q.shift()!
    if (cur.x === to.x && cur.y === to.y) break
    for (const d of dirs) {
      const n = { x: cur.x + d.x, y: cur.y + d.y }
      const k = key(n)
      if (!inBounds(n) || prev.has(k)) continue
      prev.set(k, key(cur))
      q.push(n)
    }
  }

  if (!prev.has(key(to))) {
    // fallback straight
    return [from, to]
  }
  const path: Tile[] = []
  let k: string | null = key(to)
  while (k) {
    const [x, y] = k.split(',').map(Number)
    path.push({ x, y })
    k = prev.get(k) ?? null
  }
  path.reverse()
  return path
}

/** Map percent scene point (0–100) → tile */
export function percentToTile(
  p: { x: number; y: number },
  cols = 24,
  rows = 14,
): Tile {
  return {
    x: Math.max(0, Math.min(cols - 1, Math.round((p.x / 100) * (cols - 1)))),
    y: Math.max(0, Math.min(rows - 1, Math.round((p.y / 100) * (rows - 1)))),
  }
}

/** Tile → percent scene point */
export function tileToPercent(
  t: Tile,
  cols = 24,
  rows = 14,
): { x: number; y: number } {
  return {
    x: (t.x / Math.max(1, cols - 1)) * 100,
    y: (t.y / Math.max(1, rows - 1)) * 100,
  }
}

/**
 * Build walk path in percent space using the default studio grid.
 * Inspired by XSafeClaw PathFinder (MIT code patterns only).
 */
export function buildGridWalkPath(
  fromPct: { x: number; y: number },
  toPct: { x: number; y: number },
): { x: number; y: number }[] {
  const grid = buildDefaultStudioGrid()
  const from = percentToTile(fromPct)
  const to = percentToTile(toPct)
  // Ensure endpoints walkable
  const g = grid
  if (g[from.y]?.[from.x] === 1) g[from.y][from.x] = 0
  if (g[to.y]?.[to.x] === 1) g[to.y][to.x] = 0
  const tiles = findPath(g, from, to)
  // Simplify: keep every other tile + ends to reduce hop count
  if (tiles.length <= 3) return tiles.map(tileToPercent)
  const out: { x: number; y: number }[] = []
  for (let i = 0; i < tiles.length; i++) {
    if (i === 0 || i === tiles.length - 1 || i % 2 === 0) {
      out.push(tileToPercent(tiles[i]))
    }
  }
  return out
}
