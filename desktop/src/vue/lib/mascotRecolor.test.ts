import { describe, expect, it } from 'vitest'
import { isPreserveWhite, isPreserveDark, recolorImageData } from './mascotRecolor'

describe('mascot recolor preserve rules', () => {
  it('treats bright whites as eyes to keep', () => {
    expect(isPreserveWhite(255, 255, 255, 255)).toBe(true)
    expect(isPreserveWhite(245, 242, 248, 255)).toBe(true)
    // bluish sclera anti-alias
    expect(isPreserveWhite(215, 215, 239, 255)).toBe(true)
    expect(isPreserveWhite(124, 58, 237, 255)).toBe(false)
  })

  it('treats near-black pupils and navy face plate as protected', () => {
    expect(isPreserveDark(20, 18, 22, 255)).toBe(true)
    // MadCop face plate ~57,65,172 — must not recolor into hollow sockets
    expect(isPreserveDark(57, 65, 172, 255)).toBe(true)
    expect(isPreserveDark(30, 34, 90, 255)).toBe(true)
    // body purple is not "dark face"
    expect(isPreserveDark(124, 58, 237, 255)).toBe(false)
    // light purple body pastel
    expect(isPreserveDark(196, 170, 239, 255)).toBe(false)
  })

  it('recolors purple body but not white / face / pupil pixels', () => {
    // RGBA: white, purple body, black pupil, navy face plate
    const data = new Uint8ClampedArray([
      255, 255, 255, 255,
      124, 58, 237, 255,
      10, 10, 12, 255,
      57, 65, 172, 255,
    ])
    recolorImageData(data, '#EC4899')
    // white unchanged
    expect(data[0]).toBe(255)
    expect(data[1]).toBe(255)
    expect(data[2]).toBe(255)
    // black unchanged
    expect(data[8]).toBe(10)
    // face plate unchanged
    expect(data[12]).toBe(57)
    expect(data[13]).toBe(65)
    expect(data[14]).toBe(172)
    // body changed away from pure brand purple
    const bodyChanged =
      data[4] !== 124 || data[5] !== 58 || data[6] !== 237
    expect(bodyChanged).toBe(true)
  })
})
