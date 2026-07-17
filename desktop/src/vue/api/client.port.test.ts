import { describe, it, expect } from 'vitest'
import { getBaseUrl } from './client'

describe('vue api client', () => {
  it('defaults to the FastAPI port 8765', () => {
    const base = getBaseUrl()
    expect(base).toContain('8765')
    expect(base).not.toContain('3456')
  })
})
