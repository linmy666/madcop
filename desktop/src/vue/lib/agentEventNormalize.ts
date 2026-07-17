/**
 * Normalize session agent signals into timeline events.
 * Status mapping inspired by XSafeClaw AgentJourney normalizeEvents (MIT).
 */

import { sanitizeAgentDisplayText } from './agentDisplayText'
import type { SpriteAgent } from './spriteStudio'

export type TimelineStatus = 'running' | 'completed' | 'error' | 'pending' | 'idle'

export interface AgentTimelineEvent {
  id: string
  agentId: string
  agentName: string
  color: string
  status: TimelineStatus
  label: string
  detail: string
  ts: number
}

export function mapStreamStatus(status: string | undefined): TimelineStatus {
  const s = String(status || '').toLowerCase()
  if (s === 'ok' || s === 'done' || s === 'completed') return 'completed'
  if (s === 'error' || s === 'failed') return 'error'
  if (s === 'running' || s === 'active' || s === 'working') return 'running'
  if (s === 'pending' || s === 'blocked') return 'pending'
  return 'idle'
}

export function buildTimelineFromRoster(
  roster: SpriteAgent[],
  activeToolName?: string | null,
): AgentTimelineEvent[] {
  const now = Date.now()
  const events: AgentTimelineEvent[] = []

  if (activeToolName) {
    events.push({
      id: `tool-${activeToolName}`,
      agentId: '_tool',
      agentName: '工具',
      color: '#7C3AED',
      status: 'running',
      label: `调用 ${activeToolName}`,
      detail: '',
      ts: now,
    })
  }

  for (const a of roster) {
    const status = mapStreamStatus(
      a.pose === 'error'
        ? 'error'
        : a.pose === 'blocked'
          ? 'pending'
          : a.pose === 'slacking' || a.pose === 'idle' || a.pose === 'done'
            ? a.pose === 'done'
              ? 'completed'
              : 'idle'
            : 'running',
    )
    events.push({
      id: a.id,
      agentId: a.id,
      agentName: a.name,
      color: a.color,
      status,
      label: a.bubble || a.pose,
      detail: sanitizeAgentDisplayText(a.text || '', 120),
      ts: now - (a.elapsed_ms || 0),
    })
  }
  return events
}

export function countByStatus(events: AgentTimelineEvent[]): Record<TimelineStatus, number> {
  const c: Record<TimelineStatus, number> = {
    running: 0,
    completed: 0,
    error: 0,
    pending: 0,
    idle: 0,
  }
  for (const e of events) {
    if (e.agentId === '_tool') continue
    c[e.status] = (c[e.status] || 0) + 1
  }
  return c
}
