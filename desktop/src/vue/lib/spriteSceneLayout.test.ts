import { describe, expect, it } from 'vitest'
import {
  STATION_SPOTS,
  SCENE_W,
  SCENE_H,
  buildWalkPath,
  walkDurationMs,
  stationPoint,
  facingBetween,
} from './spriteSceneLayout'

describe('station pixel alignment', () => {
  it('maps desk centers inside scene bounds', () => {
    for (const s of Object.values(STATION_SPOTS)) {
      expect(s.x).toBeGreaterThan(0)
      expect(s.x).toBeLessThan(100)
      expect(s.y).toBeGreaterThan(0)
      expect(s.y).toBeLessThan(100)
    }
  })

  it('planner/coder/designer share row-1 Y band (top desks)', () => {
    const y1 = STATION_SPOTS.planner.y
    expect(Math.abs(STATION_SPOTS.coder.y - y1)).toBeLessThan(2)
    expect(Math.abs(STATION_SPOTS.designer.y - y1)).toBeLessThan(2)
    // seats sit on furniture band, not wall (< 55% would be wall)
    expect(y1).toBeGreaterThan(55)
    expect(y1).toBeLessThan(70)
  })

  it('row-2 stations below row-1', () => {
    expect(STATION_SPOTS.researcher.y).toBeGreaterThan(STATION_SPOTS.planner.y)
    expect(STATION_SPOTS.reviewer.y).toBeGreaterThan(STATION_SPOTS.coder.y)
  })

  it('scene constants match SVG viewBox', () => {
    expect(SCENE_W).toBe(1200)
    expect(SCENE_H).toBe(700)
  })
})

describe('walk paths', () => {
  it('builds multi-point path between far stations', () => {
    const from = stationPoint('planner')
    const to = stationPoint('synthesizer')
    const path = buildWalkPath(from, to)
    expect(path.length).toBeGreaterThanOrEqual(2)
    expect(path[0].x).toBeCloseTo(from.x, 5)
    expect(path[path.length - 1].x).toBeCloseTo(to.x, 5)
  })

  it('short path for same desk', () => {
    const p = stationPoint('coder')
    const path = buildWalkPath(p, p)
    expect(path.length).toBe(1)
    expect(walkDurationMs(path)).toBe(0)
  })

  it('duration scales with distance', () => {
    const short = buildWalkPath(stationPoint('planner'), stationPoint('coder'))
    const long = buildWalkPath(stationPoint('planner'), stationPoint('synthesizer'))
    expect(walkDurationMs(long)).toBeGreaterThanOrEqual(walkDurationMs(short))
    expect(walkDurationMs(long)).toBeGreaterThan(0)
    expect(walkDurationMs(long)).toBeLessThanOrEqual(2200)
  })

  it('facingBetween picks axis-dominant direction', () => {
    expect(facingBetween({ x: 10, y: 50 }, { x: 80, y: 52 })).toBe('right')
    expect(facingBetween({ x: 80, y: 50 }, { x: 10, y: 52 })).toBe('left')
    expect(facingBetween({ x: 50, y: 20 }, { x: 52, y: 80 })).toBe('down')
  })
})
