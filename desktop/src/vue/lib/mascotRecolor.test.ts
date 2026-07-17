import { describe, expect, it } from 'vitest'
import { isPreserveWhite, isPreserveDark, recolorImageData } from './mascotRecolor'

describe('mascot recolor preserve rules', () => {
  it('treats bright whites as eyes to keep', () => {
    expect(isPreserveWhite(255, 255, 255, 255)).toBe(true)
    expect(isPreserveWhite(245, 242, 248, 255)).toBe(true)
    expect(isPreserveWhite(124, 58, 237, 255)).toBe(false)
  })

  it('treats near-black as pupils', () => {
    expect(isPreserveDark(20, 18, 22, 255)).toBe(true)
    expect(isPreserveDark(100, 80, 200, 255)).toBe(false)
  })

  it('recolors purple body but not white pixels', () => {
    // RGBA: white, purple-ish, black
    const data = new Uint8ClampedArray([
      255, 255, 255, 255,
      124, 58, 237, 255,
      10, 10, 12, 255,
    ])
    recolorImageData(data, '#EC4899')
    // white unchanged
    expect(data[0]).toBe(255)
    expect(data[1]).toBe(255)
    expect(data[2]).toBe(255)
    // black unchanged
    expect(data[8]).toBe(10)
    // body changed away from pure brand purple
    const bodyChanged =
      data[4] !== 124 || data[5] !== 58 || data[6] !== 237
    expect(bodyChanged).toBe(true)
  })
})
