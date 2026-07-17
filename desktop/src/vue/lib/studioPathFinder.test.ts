import { describe, expect, it } from 'vitest'
import {
  buildDefaultStudioGrid,
  findPath,
  buildGridWalkPath,
  percentToTile,
  tileToPercent,
} from './studioPathFinder'

describe('studioPathFinder', () => {
  it('builds a walkable grid with door open', () => {
    const g = buildDefaultStudioGrid()
    expect(g.length).toBe(14)
    expect(g[0][0]).toBe(1) // wall
    const mid = 12
    expect(g[13][mid]).toBe(0) // door row
  })

  it('finds a path around walls', () => {
    const g = buildDefaultStudioGrid()
    const path = findPath(g, { x: 2, y: 12 }, { x: 20, y: 5 })
    expect(path.length).toBeGreaterThan(2)
    expect(path[0]).toEqual({ x: 2, y: 12 })
    expect(path[path.length - 1]).toEqual({ x: 20, y: 5 })
  })

  it('percent round-trip is stable', () => {
    const t = percentToTile({ x: 50, y: 70 })
    const p = tileToPercent(t)
    expect(p.x).toBeGreaterThan(40)
    expect(p.x).toBeLessThan(60)
  })

  it('buildGridWalkPath returns percent waypoints', () => {
    const path = buildGridWalkPath({ x: 50, y: 92 }, { x: 18, y: 61 })
    expect(path.length).toBeGreaterThanOrEqual(2)
    expect(path[0].y).toBeGreaterThan(50)
  })
})
