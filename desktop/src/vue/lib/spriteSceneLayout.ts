/**
 * Pixel-aligned station layout for studio rooms (viewBox 1200×700).
 * Desk centers match furniture rects in public/studio/room-*.svg.
 */

export const SCENE_W = 1200
export const SCENE_H = 700

export interface ScenePoint {
  /** 0–100 percentage of scene width */
  x: number
  /** 0–100 percentage of scene height */
  y: number
}

export interface StationSpot extends ScenePoint {
  id: string
  label: string
  /** Seat offset above desk surface for the sprite feet */
  seatYOffset?: number
}

/** Desk centers from SVG furniture (x + w/2, y + h*0.35 for sit) */
export const STATION_SPOTS: Record<string, StationSpot> = {
  // row 1 desks: y≈400 h=90 → seat ~430 → 61.4%
  planner: { id: 'planner', label: '规划', x: (120 + 100) / SCENE_W * 100, y: 430 / SCENE_H * 100 },
  coder: { id: 'coder', label: '写码', x: (500 + 100) / SCENE_W * 100, y: 430 / SCENE_H * 100 },
  designer: { id: 'designer', label: '设计', x: (880 + 80) / SCENE_W * 100, y: 430 / SCENE_H * 100 },
  // row 2
  researcher: { id: 'researcher', label: '调研', x: (120 + 100) / SCENE_W * 100, y: 560 / SCENE_H * 100 },
  reviewer: { id: 'reviewer', label: '审核', x: (500 + 100) / SCENE_W * 100, y: 560 / SCENE_H * 100 },
  synthesizer: { id: 'synthesizer', label: '合成', x: (880 + 80) / SCENE_W * 100, y: 560 / SCENE_H * 100 },
  // coffee / general lounge bottom-left
  general: { id: 'general', label: '助手', x: 120 / SCENE_W * 100, y: 600 / SCENE_H * 100 },
  lounge: { id: 'lounge', label: '休息', x: 100 / SCENE_W * 100, y: 640 / SCENE_H * 100 },
  /** Door / spawn entry bottom center */
  door: { id: 'door', label: '入口', x: 50, y: 92 },
}

export function stationPoint(stationId: string): ScenePoint {
  const s = STATION_SPOTS[stationId] || STATION_SPOTS.general
  return { x: s.x, y: s.y }
}

/**
 * Build a simple walk path: door → mid floor → destination.
 * Optional via intermediate station for longer routes.
 */
export function buildWalkPath(from: ScenePoint, to: ScenePoint): ScenePoint[] {
  const mid: ScenePoint = {
    x: (from.x + to.x) / 2,
    y: Math.max(from.y, to.y) * 0.5 + 48 * 0.5, // stay on floor band
  }
  // Keep mid on walkable floor (~55–90% height)
  mid.y = Math.min(90, Math.max(55, mid.y))
  // If almost same desk, short hop
  const dx = Math.abs(from.x - to.x)
  const dy = Math.abs(from.y - to.y)
  if (dx < 3 && dy < 3) return [to]
  if (dx < 12 && dy < 8) return [from, to]
  return [from, mid, to]
}

export function pathToCssKeyframes(
  path: ScenePoint[],
  name: string,
): string {
  if (path.length === 0) return ''
  const n = path.length - 1
  const rules = path
    .map((p, i) => {
      const pct = n === 0 ? 100 : Math.round((i / n) * 100)
      return `${pct}% { left: ${p.x}%; top: ${p.y}%; }`
    })
    .join('\n')
  return `@keyframes ${name} {\n${rules}\n}`
}

/** Duration ms based on path length (manhattan in % space). */
export function walkDurationMs(path: ScenePoint[]): number {
  if (path.length < 2) return 0
  let dist = 0
  for (let i = 1; i < path.length; i++) {
    dist += Math.hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y)
  }
  // ~28ms per % unit, clamp 400–2200ms
  return Math.min(2200, Math.max(400, Math.round(dist * 28)))
}

export function facingBetween(a: ScenePoint, b: ScenePoint): 'left' | 'right' | 'down' | 'up' {
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (Math.abs(dx) > Math.abs(dy)) return dx >= 0 ? 'right' : 'left'
  return dy >= 0 ? 'down' : 'up'
}
