/**
 * Recolor mascot body while preserving face plate, white sclera, and dark pupils.
 * Canvas-based; results cached by target hex.
 *
 * Important: source eyes must be opaque (not transparent holes). Recolor only
 * shifts purple body hues; blue face screen + whites stay put so sprites never
 * look like hollow sockets on colored skins.
 */

const cache = new Map<string, string>()

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  return {
    r: parseInt(m[1].slice(0, 2), 16),
    g: parseInt(m[1].slice(2, 4), 16),
    b: parseInt(m[1].slice(4, 6), 16),
  }
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  let h = 0
  let s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r:
        h = ((g - b) / d + (g < b ? 6 : 0)) / 6
        break
      case g:
        h = ((b - r) / d + 2) / 6
        break
      default:
        h = ((r - g) / d + 4) / 6
    }
  }
  return [h, s, l]
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  let r: number
  let g: number
  let b: number
  if (s === 0) {
    r = g = b = l
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      let tt = t
      if (tt < 0) tt += 1
      if (tt > 1) tt -= 1
      if (tt < 1 / 6) return p + (q - p) * 6 * tt
      if (tt < 1 / 2) return q
      if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6
      return p
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)]
}

/** Bright / bluish-white sclera and specular highlights — never hue-shift. */
export function isPreserveWhite(r: number, g: number, b: number, a: number): boolean {
  if (a < 20) return false
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const lum = 0.299 * r + 0.587 * g + 0.114 * b
  // classic near-white
  if (max >= 210 && min >= 185 && max - min <= 55) return true
  // slightly blue-tinted sclera (common after anti-alias)
  if (lum >= 195 && min >= 170 && max - min <= 70) return true
  return false
}

/**
 * Near-black pupils OR dark navy face-plate / iris.
 * Face plate (~57,65,172) must not recolor with body skins.
 */
export function isPreserveDark(r: number, g: number, b: number, a: number): boolean {
  if (a < 20) return false
  // pure / near-black pupils
  if (r < 55 && g < 55 && b < 55) return true
  // dark navy face plate & pupils: blue-dominant, not body purple pastels
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const blueDom = b >= r + 15 && b >= g + 10
  const midDark = max <= 210 && min <= 120
  if (blueDom && midDark && b >= 70 && r <= 140) return true
  return false
}

/** @deprecated alias — face plate is covered by isPreserveDark */
export function isPreserveFacePlate(r: number, g: number, b: number, a: number): boolean {
  return isPreserveDark(r, g, b, a) && !(r < 55 && g < 55 && b < 55)
}

/**
 * Shift purple body (~hue 0.73) toward target color hue; skip whites / face / pupils.
 */
export function recolorImageData(
  data: Uint8ClampedArray,
  targetHex: string,
): void {
  const rgb = hexToRgb(targetHex)
  if (!rgb) return
  const [th] = rgbToHsl(rgb.r, rgb.g, rgb.b)
  // Base brand purple hue ≈ 0.73
  const baseH = 0.73

  for (let i = 0; i < data.length; i += 4) {
    const r = data[i]
    const g = data[i + 1]
    const b = data[i + 2]
    const a = data[i + 3]
    if (a < 10) continue
    if (isPreserveWhite(r, g, b, a) || isPreserveDark(r, g, b, a)) continue

    const [h, s, l] = rgbToHsl(r, g, b)
    // Only recolor purple-ish / saturated body pixels (helmet / body pastels)
    const purpleish =
      s > 0.12 &&
      l > 0.18 &&
      l < 0.92 &&
      (Math.abs(h - baseH) < 0.14 || Math.abs(h - baseH) > 0.86)
    if (!purpleish && s < 0.28) continue
    // Extra guard: never shift blue-ish mid tones that look like face edge AA
    if (b > r + 25 && b > g + 15 && l < 0.55) continue

    const [nr, ng, nb] = hslToRgb(th, Math.min(1, s * 1.05), l)
    data[i] = nr
    data[i + 1] = ng
    data[i + 2] = nb
  }
}

export async function getRecoloredMascotUrl(
  imageUrl: string,
  targetHex: string,
): Promise<string> {
  const key = `${imageUrl}::${targetHex.toLowerCase()}`
  if (cache.has(key)) return cache.get(key)!

  // Default brand purple — no processing
  if (!targetHex || /^#?7[cC]3[aA][eE][dD]$/.test(targetHex.trim())) {
    cache.set(key, imageUrl)
    return imageUrl
  }

  const img = await loadImage(imageUrl)
  const canvas = document.createElement('canvas')
  canvas.width = img.naturalWidth || img.width
  canvas.height = img.naturalHeight || img.height
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    cache.set(key, imageUrl)
    return imageUrl
  }
  ctx.drawImage(img, 0, 0)
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
  recolorImageData(imageData.data, targetHex)
  ctx.putImageData(imageData, 0, 0)
  const url = canvas.toDataURL('image/png')
  cache.set(key, url)
  return url
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('mascot load failed'))
    img.src = src
  })
}
