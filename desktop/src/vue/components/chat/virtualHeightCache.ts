/**
 * virtualHeightCache.ts — Per-session cache for measured virtual item heights
 * Mirrors the React version used by MessageList for virtual scrolling.
 */
import type { VirtualRenderItemMetric } from './messageListUtils'

const heightCache = new Map<string, Map<string, number>>()
const metricCache = new Map<string, Map<string, VirtualRenderItemMetric>>()

export function getHeightsForSession(sessionId: string): Map<string, number> {
  if (!heightCache.has(sessionId)) {
    heightCache.set(sessionId, new Map<string, number>())
  }
  return heightCache.get(sessionId)!
}

export function getMetricsForSession(sessionId: string): Map<string, VirtualRenderItemMetric> {
  if (!metricCache.has(sessionId)) {
    metricCache.set(sessionId, new Map<string, VirtualRenderItemMetric>())
  }
  return metricCache.get(sessionId)!
}

export function clearSessionCaches(sessionId: string): void {
  heightCache.delete(sessionId)
  metricCache.delete(sessionId)
}